from datetime import timedelta

from lonora_contracts.domain import utcnow
from lonora_contracts.market import Quote
from lonora_db.runs import aware


def quote_is_fresh(quote: Quote, maximum_seconds: int = 30) -> bool:
    return utcnow() - aware(quote.observed_at) <= timedelta(seconds=maximum_seconds)
