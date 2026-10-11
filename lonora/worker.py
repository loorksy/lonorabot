import asyncio
import logging
import socket
import uuid
from datetime import UTC, timedelta

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from .config import Settings, get_settings
from .database import create_database
from .orm import AgentRow, MemoryRow, MessageRow, RoutineRow, RunRow, ThreadRow, utcnow
from .provider import GrokProvider, ModelConfigurationError, ModelProviderError

log = logging.getLogger("lonora.worker")


class Worker:
    def __init__(
        self,
        settings: Settings | None = None,
        sessions: async_sessionmaker[AsyncSession] | None = None,
        *,
        worker_id: str | None = None,
    ):
        self.settings = settings or get_settings()
        if sessions is None:
            self.engine, self.sessions = create_database(self.settings.database_url)
        else:
            self.engine, self.sessions = None, sessions
        self.provider = GrokProvider(self.settings)
        self.worker_id = worker_id or f"{socket.gethostname()}-{uuid.uuid4()}"
        self.stopping = asyncio.Event()

    async def serve(self) -> None:
        log.info("worker_started worker_id=%s", self.worker_id)
        while not self.stopping.is_set():
            run = await self._claim_next()
            if run is not None:
                await self._execute(run)
                continue
            try:
                await asyncio.wait_for(self.stopping.wait(), self.settings.worker_poll_seconds)
            except TimeoutError:
                pass
        if self.engine is not None:
            await self.engine.dispose()
        log.info("worker_stopped worker_id=%s", self.worker_id)

    def stop(self) -> None:
        self.stopping.set()

    async def _claim_next(self) -> dict | None:
        now = utcnow()
        async with self.sessions() as session, session.begin():
            due = list(
                (
                    await session.scalars(
                        select(RoutineRow)
                        .where(RoutineRow.enabled.is_(True), RoutineRow.next_run_at <= now)
                        .order_by(RoutineRow.next_run_at)
                        .limit(20)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            for routine in due:
                session.add(
                    RunRow(
                        thread_id=routine.thread_id,
                        routine_id=routine.id,
                        prompt=routine.prompt,
                        status="queued",
                    )
                )
                interval = timedelta(seconds=routine.interval_seconds)
                scheduled_at = routine.next_run_at
                if scheduled_at.tzinfo is None:
                    scheduled_at = scheduled_at.replace(tzinfo=UTC)
                next_at = scheduled_at + interval
                if next_at <= now:
                    missed = int((now - next_at) // interval) + 1
                    next_at += missed * interval
                routine.next_run_at = next_at

            active_run = aliased(RunRow)
            claimable = await session.scalar(
                select(RunRow)
                .where(
                    or_(
                        RunRow.status == "queued",
                        and_(
                            RunRow.status.in_(("leased", "running")), RunRow.lease_expires_at <= now
                        ),
                    )
                )
                .where(
                    ~exists(
                        select(active_run.id).where(
                            active_run.thread_id == RunRow.thread_id,
                            active_run.id != RunRow.id,
                            active_run.status.in_(("leased", "running")),
                            active_run.lease_expires_at > now,
                        )
                    )
                )
                .order_by(RunRow.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if claimable is None:
                return None
            claimable.status = "leased"
            claimable.fence += 1
            claimable.lease_owner = self.worker_id
            claimable.lease_expires_at = now + timedelta(seconds=self.settings.run_lease_seconds)
            claimable.error_code = None
            await session.flush()
            return {
                "id": claimable.id,
                "thread_id": claimable.thread_id,
                "routine_id": claimable.routine_id,
                "prompt": claimable.prompt,
                "fence": claimable.fence,
            }

    async def _execute(self, run: dict) -> None:
        async with self.sessions() as session, session.begin():
            stored_run = await session.scalar(
                select(RunRow).where(RunRow.id == run["id"]).with_for_update()
            )
            if (
                stored_run is None
                or stored_run.status != "leased"
                or stored_run.lease_owner != self.worker_id
                or stored_run.fence != run["fence"]
            ):
                return
            stored_run.status = "running"
            thread = await session.scalar(
                select(ThreadRow).where(ThreadRow.id == run["thread_id"]).with_for_update()
            )
            if thread is None:
                await self._fail_in_session(stored_run, "thread_not_found")
                return
            if run["routine_id"] and run["prompt"]:
                session.add(
                    MessageRow(
                        thread_id=thread.id,
                        seq=thread.next_seq,
                        role="user",
                        content=f"Scheduled task: {run['prompt']}",
                    )
                )
                thread.next_seq += 1
                await session.flush()
            agent = await session.get(AgentRow, thread.agent_id)
            memory = await session.get(MemoryRow, thread.agent_id)
            history = list(
                (
                    await session.scalars(
                        select(MessageRow)
                        .where(MessageRow.thread_id == thread.id)
                        .order_by(MessageRow.seq.desc())
                        .limit(40)
                    )
                ).all()
            )
            instructions = (
                agent.instructions
                if agent and agent.instructions
                else "You are a helpful Lonora agent."
            )
            if memory and memory.content.strip():
                instructions += "\n\nPersistent memory:\n" + memory.content
            instructions += "\nRespond in the user's language; support Arabic and respect RTL text."
            messages = [{"role": "system", "content": instructions}]
            messages.extend(
                {"role": item.role, "content": item.content} for item in reversed(history)
            )

        try:
            answer = await self.provider.respond(messages)
            error_code = None
        except ModelConfigurationError:
            answer, error_code = "Model provider configuration is required.", "model_not_configured"
        except ModelProviderError as exc:
            answer, error_code = "The model provider request failed.", str(exc)
        except Exception as exc:
            log.exception("run_error run_id=%s error_type=%s", run["id"], type(exc).__name__)
            answer, error_code = "The agent could not complete this run.", "runtime_error"

        now = utcnow()
        async with self.sessions() as session, session.begin():
            stored_run = await session.scalar(
                select(RunRow).where(RunRow.id == run["id"]).with_for_update()
            )
            if (
                stored_run is None
                or stored_run.status != "running"
                or stored_run.lease_owner != self.worker_id
                or stored_run.fence != run["fence"]
            ):
                log.info("stale_run_discarded run_id=%s fence=%s", run["id"], run["fence"])
                return
            thread = await session.scalar(
                select(ThreadRow).where(ThreadRow.id == stored_run.thread_id).with_for_update()
            )
            if thread is None:
                await self._fail_in_session(stored_run, "thread_not_found")
                return
            session.add(
                MessageRow(
                    thread_id=thread.id, seq=thread.next_seq, role="assistant", content=answer
                )
            )
            thread.next_seq += 1
            stored_run.status = "failed" if error_code else "completed"
            stored_run.error_code = error_code
            stored_run.updated_at = now
            stored_run.lease_owner = None
            stored_run.lease_expires_at = None

    @staticmethod
    async def _fail_in_session(run: RunRow, code: str) -> None:
        run.status = "failed"
        run.error_code = code
        run.updated_at = utcnow()
        run.lease_owner = None
        run.lease_expires_at = None


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    worker = Worker()
    try:
        await worker.serve()
    except KeyboardInterrupt:
        worker.stop()


if __name__ == "__main__":
    asyncio.run(main())
