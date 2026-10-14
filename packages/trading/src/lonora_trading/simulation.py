from decimal import Decimal
from typing import Any

from lonora_contracts.account import AccountState
from lonora_contracts.domain import utcnow
from lonora_contracts.market import Candle, Instrument, Quote
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.trading_accounts import TradingAccountRepository
from lonora_db.transactions import resource_data


async def import_simulation(
    db: Database, owner_id: str, connection_id: str, snapshot: dict[str, Any]
) -> dict[str, Any]:
    if Decimal(str(snapshot.get("balance", -1))) < 0 or not snapshot.get("currency"):
        raise LonoraError("invalid_simulation_account")
    instruments = [
        Instrument.model_validate(item).model_dump(mode="json")
        for item in snapshot.get("instruments", [])
    ]
    quotes = {
        symbol: Quote.model_validate(item).model_dump(mode="json")
        for symbol, item in snapshot.get("quotes", {}).items()
    }
    candles = {
        key: [Candle.model_validate(item).model_dump(mode="json") for item in values]
        for key, values in snapshot.get("candles", {}).items()
    }
    payload = {
        "simulation": True,
        "currency": snapshot["currency"],
        "balance": str(snapshot["balance"]),
        "instruments": instruments,
        "quotes": quotes,
        "candles": candles,
        "positions": [],
        "orders": [],
        "operations": {},
        "history": snapshot.get("history", [])[:1000],
    }
    native_fields = {
        key: snapshot.get(key)
        for key in ("broker", "server", "name", "platform", "trade_allowed", "investor_mode")
    }
    native_fields["login"] = str(snapshot["login"]) if snapshot.get("login") is not None else None
    identity = AccountState.model_validate(
        {
            "id": connection_id,
            "currency": snapshot["currency"],
            "balance": snapshot["balance"],
            "equity": snapshot.get("equity", snapshot["balance"]),
            "margin": snapshot.get("margin", 0),
            "free_margin": snapshot.get("free_margin", snapshot["balance"]),
            "observed_at": utcnow(),
            **native_fields,
        }
    )
    payload.update(
        {
            key: value
            for key, value in identity.model_dump(mode="json").items()
            if key not in {"id", "observed_at"}
        }
    )
    async with db.sessions() as session, session.begin():
        existing = await session.get(TradingAccountRepository.row_type, connection_id)
        if existing:
            raise LonoraError("simulation_already_initialized", 409)
        return resource_data(
            await TradingAccountRepository().create(
                session, owner_id, payload, resource_id=connection_id
            )
        )
