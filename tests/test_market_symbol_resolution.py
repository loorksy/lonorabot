"""Catalog validation preserves broker spelling and real discovery failures."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from lonora_core.user_error import LonoraError
from lonora_tools.symbols import canonical_broker_symbol


@pytest.mark.asyncio
@pytest.mark.parametrize("symbol", ["EURUSDm", "XAUUSD.raw", "US500.cash", "BTCUSD.a"])
async def test_strict_catalog_keeps_exact_suffix_and_resolves_only_case(symbol: str) -> None:
    broker = SimpleNamespace(symbols=AsyncMock(return_value=[symbol]))
    assert await canonical_broker_symbol(broker, symbol, require_exists=True) == symbol
    assert await canonical_broker_symbol(broker, symbol.swapcase(), require_exists=True) == symbol
    with pytest.raises(LonoraError, match="symbol_not_found"):
        await canonical_broker_symbol(broker, symbol + ".other", require_exists=True)


@pytest.mark.asyncio
async def test_strict_catalog_never_hides_discovery_failure_as_an_unknown_symbol() -> None:
    error = LonoraError("broker_connection_timeout", 409)
    broker = SimpleNamespace(symbols=AsyncMock(side_effect=error))
    with pytest.raises(LonoraError) as failure:
        await canonical_broker_symbol(broker, "EURUSDm", require_exists=True)
    assert failure.value is error
    assert await canonical_broker_symbol(broker, "EURUSDm") == "EURUSDm"


@pytest.mark.asyncio
async def test_ambiguous_case_does_not_choose_a_different_broker_instrument() -> None:
    broker = SimpleNamespace(symbols=AsyncMock(return_value=["EURUSDm", "eurusdm"]))
    assert await canonical_broker_symbol(broker, "EURUSDm", require_exists=True) == "EURUSDm"
    with pytest.raises(LonoraError, match="symbol_ambiguous"):
        await canonical_broker_symbol(broker, "EURUSDM", require_exists=True)


@pytest.mark.asyncio
async def test_invalid_catalog_shape_is_unavailable_not_an_unknown_symbol() -> None:
    broker = SimpleNamespace(symbols=AsyncMock(return_value=None))
    with pytest.raises(LonoraError, match="broker_symbols_unavailable"):
        await canonical_broker_symbol(broker, "EURUSDm", require_exists=True)
