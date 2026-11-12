import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from lonora_agent.collaboration.outcome_return import return_pending_outcomes
from lonora_agent.runtime import AgentRuntime
from lonora_automation.runner import dispatch_routines
from lonora_charts.runtime import chart_runtime_tick
from lonora_charts.visual import ChartVisualRuntime
from lonora_contracts.domain import utcnow
from lonora_contracts.mcp import McpToolDeclaration
from lonora_db.activation_review import dispatch_activation_reviews
from lonora_db.client import Database
from lonora_db.item_failures import failure_code
from lonora_db.owner import get_owner
from lonora_db.task_recovery import retry_due_tasks
from lonora_db.task_wait import resume_ready_waits
from lonora_security.secrets import SecretScan
from lonora_tools.loader import load_tools
from lonora_trading.reconciliation import recheck_verifications, reconcile_ambiguous
from lonora_workspace.client import with_guard

from .connection_manager import close_connections, maintain_voice
from .event_dispatch import dispatch_channels
from .heartbeat import write_heartbeat
from .history_maintenance import maintain_history
from .lifecycle import GatewayState
from .liveness import Liveness, StepSpec, supervise_step
from .process_identity import process_identity
from .run_dispatch import dispatch_one
from .runtime import OwnerServices
from .shutdown import drain, release_leases
from .supervisor import supervise
from .wake_dispatch import dispatch_market_wakes
from .watchdog import Watchdog

log = logging.getLogger("lonora.gateway")

# Every maintenance step is its own supervised task with its own interval, iteration
# timeout and liveness record: a step that raises or hangs never stops another one.
STEPS = (
    StepSpec("heartbeat", 10, 30),
    StepSpec("owners", 10, 60),
    StepSpec("routines", 5, 120),
    StepSpec("task_retries", 10, 120),
    StepSpec("activation_reviews", 10, 120, critical=False),
    StepSpec("task_waits", 5, 120),
    StepSpec("outcomes", 10, 120),
    StepSpec("reconcile", 10, 300),
    StepSpec("verifications", 10, 300),
    StepSpec("account_recovery", 10, 300),
    # Accounts the owner connected from chat: provision, deploy, connect, report.
    StepSpec("broker_provisioning", 10, 900),
    # The closed-trade ledger from broker deal history (mandate 5.5.1).
    StepSpec("closed_trades", 30, 300, critical=False),
    StepSpec("opportunities", 10, 120, critical=False),
    StepSpec("market", 2, 120),
    StepSpec("history", 10, 600, critical=False),
    StepSpec("charts", 2, 120, critical=False),
    StepSpec("watches", 2, 120),
    StepSpec("voice", 0.5, 60, critical=False),
    # Owner voice notes: one provider transcription per note, outside any request.
    StepSpec("voice_notes", 1, 300, critical=False),
    StepSpec("channels", 2, 120),
    StepSpec("attention", 2, 120),
    # Push to the owner's phones (VISION 11.4). Not critical: Expo being unreachable never
    # makes the gateway unready.
    StepSpec("push", 2, 120, critical=False),
    StepSpec("incoming", 2, 60, critical=False),
    StepSpec("thread_prefs", 2, 60, critical=False),
    # Which background workspace processes ended, for each agent's next wake (7.1.2).
    StepSpec("workspace", 10, 60, critical=False),
    # The owner's stop and stop-all taps in What is running (7.1.5).
    StepSpec("workspace_stops", 2, 60, critical=False),
    # The morning brief: once per local date for each owner (VISION 11.1).
    StepSpec("morning_brief", 30, 120),
    StepSpec("watchdog", 30, 120),
)


class Gateway:
    def __init__(
        self,
        db: Database,
        key: str,
        artifact_root: Path,
        lease_seconds: int = 120,
        maximum_rounds: int = 24,
        maximum_subagents: int = 4,
        poll_seconds: float = 0.5,
        chart_visual: ChartVisualRuntime | None = None,
        workspace_socket: Path | None = None,
        mcp_declarations: tuple[McpToolDeclaration, ...] = (),
        searxng_url: str | None = None,
        browser_url: str | None = None,
        mcp_owner_trust: bool = True,
        expo_access_token: str | None = None,
    ):
        self.db, self.key, self.root = db, key, artifact_root
        self.chart_visual = chart_visual
        self.workspace_socket = workspace_socket
        self.mcp_declarations = mcp_declarations
        self.mcp_owner_trust = mcp_owner_trust
        self.searxng_url = searxng_url
        self.browser_url = browser_url
        self.expo_access_token = expo_access_token
        self.lease_seconds, self.maximum_subagents, self.poll_seconds = (
            lease_seconds,
            maximum_subagents,
            poll_seconds,
        )
        self.voice_tasks: dict[str, asyncio.Task[None]] = {}
        self.identity = process_identity()
        self.stop = asyncio.Event()
        self.state = GatewayState.STARTING
        self.services: dict[str, OwnerServices] = {}
        self.runtime = AgentRuntime(load_tools(), lease_seconds, maximum_rounds)
        self.liveness = Liveness()
        self.watchdog = Watchdog(
            db, self.liveness, self.runtime.read_only_names(), identity=self.identity
        )

    async def worker_loop(self, lane: str | None = None, name: str = "worker") -> None:
        # A worker is live while it polls; while it runs a Run it is busy, not stalled.
        record = self.liveness.register(StepSpec(name, self.poll_seconds, 0))
        while not self.stop.is_set():
            record.busy = True
            try:
                claimed = await dispatch_one(
                    self.db,
                    self.identity,
                    self.runtime,
                    self.services,
                    self.key,
                    self.root,
                    self.lease_seconds,
                    self.maximum_subagents,
                    lane,
                    self.chart_visual,
                    self.workspace_socket,
                    self.mcp_declarations,
                    self.searxng_url,
                    self.browser_url,
                    self.mcp_owner_trust,
                )
            except Exception as error:
                # A worker whose every claim fails is not live: its record goes stale,
                # so readiness and the watchdog report it while the supervisor restarts it.
                record.failures += 1
                record.last_error = failure_code(error)
                raise
            finally:
                record.busy = False
            record.failures, record.last_error = 0, None
            record.succeeded_at = utcnow()
            if not claimed:
                await asyncio.sleep(self.poll_seconds)

    def service(self, owner_id: str) -> OwnerServices:
        if owner_id not in self.services:
            self.services[owner_id] = OwnerServices.create(
                self.db,
                owner_id,
                self.key,
                chart_visual=self.chart_visual,
                workspace_socket=self.workspace_socket,
                mcp_declarations=self.mcp_declarations,
                searxng_url=self.searxng_url,
                browser_url=self.browser_url,
                mcp_owner_trust=self.mcp_owner_trust,
            )
        return self.services[owner_id]

    async def for_each_owner(self, action: Callable[[OwnerServices], Awaitable[object]]) -> None:
        """Run one step for every owner; one owner's failure never skips the others."""
        failure: Exception | None = None
        for service in list(self.services.values()):
            try:
                await action(service)
            except Exception as error:
                failure = failure or error
                log.error("owner_step_failed code=%s", failure_code(error))
        if failure:
            raise failure

    async def heartbeat(self) -> None:
        await write_heartbeat(self.db, self.identity, self.state.value, self.liveness.snapshot())

    async def owners(self) -> None:
        async with self.db.sessions() as session:
            owner = await get_owner(session)
        if owner:
            self.service(owner.id)

    async def reconcile(self) -> None:
        await self.for_each_owner(lambda service: reconcile_ambiguous(self.db, service.brokers))

    async def verifications(self) -> None:
        await self.for_each_owner(lambda service: recheck_verifications(self.db, service.brokers))

    async def account_recovery(self) -> None:
        from lonora_trading.broker_recovery import maintenance_account_recovery

        await self.for_each_owner(
            lambda service: maintenance_account_recovery(self.db, service.brokers, service.owner_id)
        )

    async def broker_provisioning(self) -> None:
        from lonora_adapters.storage.broker_secrets import BrokerSecrets
        from lonora_trading.broker_provisioning import maintain_broker_provisioning

        await self.for_each_owner(
            lambda service: maintain_broker_provisioning(
                self.db,
                service.brokers,
                BrokerSecrets(self.db, self.key, service.owner_id),
                service.owner_id,
            )
        )

    async def closed_trades(self) -> None:
        from lonora_trading.closed_trades import maintenance_closed_trades

        await self.for_each_owner(
            lambda service: maintenance_closed_trades(self.db, service.brokers, service.owner_id)
        )

    async def opportunities(self) -> None:
        from lonora_trading.opportunities import maintenance_opportunities

        await self.for_each_owner(
            lambda service: maintenance_opportunities(self.db, service.owner_id)
        )

    async def market(self) -> None:
        await self.for_each_owner(lambda service: service.market.maintain())

    async def history(self) -> None:
        await self.for_each_owner(lambda service: maintain_history(service, self.root))

    async def charts(self) -> None:
        await self.for_each_owner(
            lambda service: chart_runtime_tick(
                self.db,
                service.brokers,
                service.owner_id,
                self.identity,
                maintain_streams=False,
            )
        )

    async def watches(self) -> None:
        await self.for_each_owner(
            lambda service: dispatch_market_wakes(self.db, service.brokers, service.secrets.read)
        )

    async def voice(self) -> None:
        await self.for_each_owner(
            lambda service: maintain_voice(self.db, service, self.identity, self.voice_tasks)
        )

    async def voice_notes(self) -> None:
        from lonora_providers.credentials import ProviderCredentials
        from lonora_voice.voice_notes import transcribe_pending

        await self.for_each_owner(
            lambda service: transcribe_pending(
                self.db, ProviderCredentials(self.db, service.secrets), service.owner_id, self.root
            )
        )

    async def channels(self) -> None:
        await self.for_each_owner(lambda service: dispatch_channels(self.db, service))

    async def attention(self) -> None:
        from .attention import attention_tick

        await self.for_each_owner(
            lambda service: attention_tick(
                self.db, service.brokers, service.owner_id, read_secret=service.secrets.read
            )
        )

    async def push(self) -> None:
        from lonora_adapters.channels.expo_push import ExpoPushTransport
        from lonora_security.secrets import SecretCipher

        from .push import dispatch_push

        cipher, transport = SecretCipher(self.key), ExpoPushTransport(self.expo_access_token)
        await self.for_each_owner(
            lambda service: dispatch_push(self.db, service.owner_id, cipher, transport)
        )

    async def incoming(self) -> None:
        from lonora_voice.incoming import incoming_tick

        await self.for_each_owner(lambda service: incoming_tick(self.db, service.owner_id))

    async def thread_prefs(self) -> None:
        from .thread_prefs import thread_prefs_tick

        await self.for_each_owner(lambda service: thread_prefs_tick(self.db, service.owner_id))

    async def workspace(self) -> None:
        from datetime import UTC, datetime

        from lonora_db.workspace_processes import reconcile

        from .runtime import WORKSPACE

        if not WORKSPACE.present():
            return
        # Only ids, times and exit codes are kept from this listing; commands are stored
        # from the tool's own scanned answer.
        fetched_at = datetime.now(UTC)
        listing = await WORKSPACE.processes(SecretScan({}))
        async with self.db.sessions() as session, session.begin():
            await reconcile(session, listing, fetched_at)
        await self.for_each_owner(self.record_running)

    async def workspace_scan(self, service: OwnerServices) -> SecretScan:
        """The owner's scan of what the workspace returns (7.2.6), as the tools use it."""
        values = await service.secrets.scanned_values()
        given = await service.given.values() if service.given else []
        return with_guard(SecretScan(values), [[name, value] for name, value in given])

    async def record_running(self, service: OwnerServices) -> None:
        """What is running (7.1.5): the owner's agents' processes, scanned for the owner."""
        from lonora_db.workspace_running import record_listing

        from .runtime import WORKSPACE

        asked = utcnow()
        listing = await WORKSPACE.processes(await self.workspace_scan(service))
        async with self.db.sessions() as session, session.begin():
            await record_listing(session, service.owner_id, listing["processes"], asked)

    async def workspace_stops(self) -> None:
        from .runtime import WORKSPACE

        if WORKSPACE.present():
            await self.for_each_owner(self.carry_out_stops)

    async def carry_out_stops(self, service: OwnerServices) -> None:
        """Each stop the owner asked for, once: one process as the agent it runs as (the
        supervisor checks the pid still belongs to that agent), or every agent's processes."""
        from lonora_db.workspace_running import claim_stops, owner_agents

        from .runtime import WORKSPACE

        async with self.db.sessions() as session, session.begin():
            claimed = await claim_stops(session, service.owner_id)
            stops = [(stop.pid, stop.agent_id) for stop in claimed]
            agents = list(await owner_agents(session, service.owner_id)) if stops else []
        if not stops:
            return
        scan = await self.workspace_scan(service)
        for pid, agent_id in stops:
            if pid is None or agent_id is None:
                for each in agents:
                    await WORKSPACE.stop_all(scan, each)
            else:
                await WORKSPACE.stop(scan, pid, agent_id)
        await self.record_running(service)

    async def morning_brief(self) -> None:
        from lonora_trading.morning_brief import brief_tick

        await self.for_each_owner(lambda service: brief_tick(self.db, service.owner_id))

    def iterations(self) -> dict[str, Callable[[], Awaitable[object]]]:
        return {
            "heartbeat": self.heartbeat,
            "owners": self.owners,
            "routines": lambda: dispatch_routines(self.db),
            "task_retries": lambda: retry_due_tasks(self.db),
            "activation_reviews": lambda: dispatch_activation_reviews(self.db),
            "task_waits": lambda: resume_ready_waits(self.db),
            "outcomes": lambda: return_pending_outcomes(self.db),
            "reconcile": self.reconcile,
            "verifications": self.verifications,
            "account_recovery": self.account_recovery,
            "broker_provisioning": self.broker_provisioning,
            "closed_trades": self.closed_trades,
            "opportunities": self.opportunities,
            "market": self.market,
            "history": self.history,
            "charts": self.charts,
            "watches": self.watches,
            "voice": self.voice,
            "voice_notes": self.voice_notes,
            "channels": self.channels,
            "attention": self.attention,
            "push": self.push,
            "incoming": self.incoming,
            "thread_prefs": self.thread_prefs,
            "workspace": self.workspace,
            "workspace_stops": self.workspace_stops,
            "morning_brief": self.morning_brief,
            "watchdog": self.watchdog.tick,
        }

    def start(self) -> list[asyncio.Task[None]]:
        """Start every worker and every step, each in its own supervised task."""
        loops: list[asyncio.Task[None]] = []
        for index in range(self.maximum_subagents + 1):
            name = "worker-" + str(index)

            async def shared(name: str = name) -> None:
                await self.worker_loop(None, name)

            loops.append(asyncio.create_task(supervise(name, shared, self.stop)))

        async def foreground() -> None:
            await self.worker_loop("conversation", "conversation")

        loops.append(asyncio.create_task(supervise("conversation", foreground, self.stop)))
        iterations = self.iterations()
        for spec in STEPS:
            loops.append(
                asyncio.create_task(
                    supervise_step(spec, iterations[spec.name], self.stop, self.liveness)
                )
            )
        return loops

    async def serve(self) -> None:
        self.state = GatewayState.RUNNING
        loops = self.start()
        await self.stop.wait()
        self.state = GatewayState.DRAINING
        await write_heartbeat(self.db, self.identity, self.state.value, self.liveness.snapshot())
        await drain(loops)
        # Leases this process still holds go back to the queue with their fence kept,
        # so the next gateway resumes that work at once instead of after lease expiry.
        await release_leases(self.db, self.identity)
        await close_connections(self.services, self.voice_tasks)
        if self.chart_visual:
            await self.chart_visual.close()
        self.state = GatewayState.STOPPED
        await write_heartbeat(self.db, self.identity, self.state.value, self.liveness.snapshot())

    def request_stop(self) -> None:
        self.stop.set()
