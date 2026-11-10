"""The broker a Goal reads its evidence from, after its agent is checked."""

from typing import Protocol

from lonora_adapter_kit.broker import BrokerStateReader
from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.market import Candle
from lonora_db.client import Database
from lonora_db.goal_scope import require_goal_agent
from lonora_db.schema import TradingGoalRow


class GoalEvidenceReader(BrokerStateReader, Protocol):
    async def candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]: ...


async def goal_broker(
    db: Database, brokers: BrokerManager, goal: TradingGoalRow
) -> GoalEvidenceReader:
    async with db.sessions() as session:
        await require_goal_agent(session, goal)
    return await brokers.get(goal.owner_id, str(goal.payload["account_id"]))
