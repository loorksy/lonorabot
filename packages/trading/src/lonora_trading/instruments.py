from decimal import Decimal

from lonora_contracts.market import Instrument


def format_price(price: Decimal, instrument: Instrument) -> str:
    return f"{price:.{instrument.digits}f}"
