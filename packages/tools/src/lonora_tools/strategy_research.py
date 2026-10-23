"""Ordinary Agent research tools using canonical history and attachment storage."""

import asyncio
import hashlib
from typing import Any

from lonora_contracts.domain import Contract, utcnow
from lonora_core.user_error import LonoraError
from lonora_db.artifacts import ArtifactRepository
from lonora_db.runs import require_lease
from lonora_db.schema import ArtifactRow
from lonora_market.broker import broker_market
from lonora_market.research import ResearchConfig, candle_end, digest, research
from lonora_security.runtime_storage import confined_path
from pydantic import Field
from sqlalchemy import select

from .artifacts import store_artifact
from .base import Tool
from .context import ToolContext
from .symbols import canonical_broker_symbol


class ResearchInput(Contract):
    account_id: str = Field(min_length=1, max_length=80)
    symbol: str = Field(min_length=1, max_length=80)
    timeframe: str = Field(min_length=1, max_length=8)
    limit: int = Field(default=500, ge=80, le=1000)
    config: ResearchConfig


class ResearchHistoryInput(Contract):
    account_id: str = Field(min_length=1, max_length=80)
    symbol: str = Field(min_length=1, max_length=80)
    limit: int = Field(default=10, ge=1, le=20)


async def saved_research(context: ToolContext, request_digest: str) -> dict[str, Any] | None:
    async with context.db.sessions() as session:
        await require_lease(session, context.lease)
        row = await session.get(ArtifactRepository.row_type, context.resource_id)
        if row is None:
            return None
        if (
            row.owner_id != context.owner_id
            or row.agent_id != context.agent_id
            or row.thread_id != context.thread_id
            or row.state.get("research_request_sha256") != request_digest
        ):
            raise LonoraError("research_receipt_conflict", 409)
        path = confined_path(context.artifact_root, row.payload["key"])
        try:
            if path.stat().st_size != row.payload["size"] or path.stat().st_size > 2_000_000:
                raise LonoraError("artifact_integrity_failed", 409)
            content = path.read_bytes()
        except OSError:
            raise LonoraError("artifact_file_missing", 404) from None
        if hashlib.sha256(content).hexdigest() != row.payload["sha256"]:
            raise LonoraError("artifact_integrity_failed", 409)
        return dict(row.state["research_summary"])


async def run_research(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    body = ResearchInput.model_validate(args)
    request_digest = digest(body.model_dump(mode="json"))
    saved = await saved_research(context, request_digest)
    if saved is not None:
        return saved
    broker = await context.brokers.get(context.owner_id, body.account_id)
    symbol = await canonical_broker_symbol(broker, body.symbol)
    instrument = await broker.instrument(symbol)
    if instrument.symbol != symbol:
        raise LonoraError("broker_symbol_mismatch", 422)
    provider = await broker_market(context.brokers, context.owner_id, body.account_id)
    bars = await provider.candles(symbol, body.timeframe, body.limit)
    observed_at = utcnow()
    # Current incomplete bars can change after this request. Never use them as a
    # completed signal or quietly replace historical receipts on call replay.
    if any(bar.time.tzinfo is None or bar.time.utcoffset() is None for bar in bars):
        raise LonoraError("market_candle_timestamp_invalid", 422)
    if any(bar.time > observed_at for bar in bars):
        raise LonoraError("research_incomplete_or_future_bar", 422)
    closed = [bar for bar in bars if candle_end(bar) <= observed_at]
    result = await asyncio.to_thread(
        research,
        closed,
        instrument,
        body.config,
        observed_at=observed_at,
        account_id=body.account_id,
        source="broker_history:" + type(broker).__name__,
    )
    summary: dict[str, Any] = {
        "mode": result.mode,
        "execution_authorized": False,
        "account_id": body.account_id,
        "symbol": symbol,
        "timeframe": body.timeframe,
        "observed_at": observed_at.isoformat(),
        "bars": len(closed),
        "excluded_incomplete_bars": len(bars) - len(closed),
        "dataset_sha256": result.dataset_sha256,
        "result_sha256": result.result_sha256,
        "engine_version": result.engine_version,
        "currency": body.config.scenario.currency,
        "economics": "declared_scenario_only",
        "baseline": result.baseline.model_dump(mode="json"),
        "out_of_sample": [fold.out_of_sample.model_dump(mode="json") for fold in result.folds],
        "monte_carlo": result.monte_carlo,
        "integrity": result.integrity,
        "confidence": result.confidence,
        "missing_inputs": result.missing_inputs,
        "artifact_id": context.resource_id,
        "read_report_with": "artifact_read",
    }
    await store_artifact(
        context,
        "strategy-research.json",
        result.model_dump_json(indent=2).encode(),
        "application/json",
        receipt_state={
            "research_result": True,
            "research_request_sha256": request_digest,
            "research_scope": {"account_id": body.account_id, "symbol": symbol},
            "research_summary": summary,
        },
    )
    return summary


async def history(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    body = ResearchHistoryInput.model_validate(args)
    async with context.db.sessions() as session:
        await require_lease(session, context.lease)
        rows = (
            await session.scalars(
                select(ArtifactRow)
                .where(
                    ArtifactRow.owner_id == context.owner_id,
                    ArtifactRow.agent_id == context.agent_id,
                    ArtifactRow.state["research_result"].as_boolean().is_(True),
                    ArtifactRow.state["research_scope"]["account_id"].as_string()
                    == body.account_id,
                    ArtifactRow.state["research_scope"]["symbol"].as_string() == body.symbol,
                )
                .order_by(ArtifactRow.created_at.desc(), ArtifactRow.id)
                .limit(body.limit)
            )
        ).all()
    return {
        "mode": "historical_research",
        "execution_authorized": False,
        "reports": [
            {
                key: row.state["research_summary"][key]
                for key in (
                    "artifact_id",
                    "symbol",
                    "timeframe",
                    "observed_at",
                    "dataset_sha256",
                    "result_sha256",
                    "engine_version",
                    "confidence",
                )
            }
            for row in rows
        ],
    }


def tools() -> list[Tool]:
    return [
        Tool(
            "market_strategy_research",
            "Run bounded SMA-cross historical research from exact broker candles/specifications; persist reproducible data/config/results in an attached report. Includes chronological train/validation/OOS folds and seeded Monte Carlo cost stress. Supply explicit scenario tick valuation, currency, price basis, volume and costs: these are assumptions, not verified broker economics. Closed bars only, max 1000 bars/12 candidates; no arbitrary strategy conversion, live recommendation, Shadow execution or financial authority. Repeating the same call returns its original report.",
            ResearchInput,
            run_research,
            True,
        ),
        Tool(
            "market_research_history",
            "Find this Agent's saved historical research reports for one exact account/symbol. Read an immutable report using artifact_read; report lineage is analytical and grants no trading authority.",
            ResearchHistoryInput,
            history,
            True,
        ),
    ]
