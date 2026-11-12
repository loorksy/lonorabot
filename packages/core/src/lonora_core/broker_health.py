"""Which broker health problem (mandate 9.4) a stored recovery snapshot shows, if any.

A rejected token and an undeployed account are problems at once. A lost connection is
one only after it has lasted ``LOST_CONNECTION_GRACE``: MetaApi reconnects several times
an hour, and a short drop is not the owner's business.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from lonora_contracts.attention import AttentionCode

LOST_CONNECTION_GRACE = timedelta(minutes=2)
# The adapter's reason codes for a problem that needs the owner at once.
IMMEDIATE: dict[str, AttentionCode] = {
    "broker_credentials_rejected": "broker_token_rejected",
    "broker_account_undeployed": "broker_account_undeployed",
    # The account no longer exists at MetaApi: nothing is deployed to connect to, and
    # the owner text says so for both reasons.
    "broker_account_not_found": "broker_account_undeployed",
}


def outage(recovery: dict[str, Any]) -> tuple[AttentionCode, datetime] | None:
    """The problem a disconnected account has and when it became disconnected, with no
    grace applied; None while it is not disconnected or its state cannot be read."""
    if recovery.get("status") != "disconnected":
        return None
    try:
        since = datetime.fromisoformat(str(recovery.get("since")))
    except ValueError:
        return None
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)
    code = IMMEDIATE.get(str(recovery.get("reason_code") or ""), "broker_connection_lost")
    return code, since


def broker_problem(recovery: dict[str, Any], now: datetime) -> tuple[AttentionCode, str] | None:
    """The problem code and the time it started, once it is a problem for the owner.

    ``recovery`` is the ``broker_recovery`` snapshot of a connection. Only a
    ``disconnected`` account has a problem; ``since`` is when it became disconnected.
    """
    found = outage(recovery)
    if found is None:
        return None
    code, since = found
    if code == "broker_connection_lost" and now - since < LOST_CONNECTION_GRACE:
        return None
    return code, since.isoformat()
