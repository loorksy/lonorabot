"""Which broker health problem (mandate 9.4) a stored recovery snapshot shows, if any.

A rejected token and an undeployed account are problems at once. A lost connection is
one only after it has lasted ``LOST_CONNECTION_GRACE``: MetaApi reconnects several times
an hour, and a short drop is not the owner's business.
"""

from datetime import datetime, timedelta
from typing import Any

from lonora_contracts.attention import AttentionCode

LOST_CONNECTION_GRACE = timedelta(minutes=2)
# The adapter's reason codes for a problem that needs the owner at once.
IMMEDIATE: dict[str, AttentionCode] = {
    "broker_credentials_rejected": "broker_token_rejected",
    "broker_account_undeployed": "broker_account_undeployed",
    # The account no longer exists at MetaApi: nothing is deployed to connect to.
    "broker_account_not_found": "broker_account_undeployed",
}


def broker_problem(recovery: dict[str, Any], now: datetime) -> tuple[AttentionCode, str] | None:
    """The problem code and the time it started, or None while the account is healthy.

    ``recovery`` is the ``broker_recovery`` snapshot of a connection. Only a
    ``disconnected`` account has a problem; ``since`` is when it became disconnected.
    """
    if recovery.get("status") != "disconnected" or not recovery.get("since"):
        return None
    since = datetime.fromisoformat(str(recovery["since"]))
    code = IMMEDIATE.get(str(recovery.get("reason_code") or ""))
    if code is not None:
        return code, since.isoformat()
    if now - since < LOST_CONNECTION_GRACE:
        return None
    return "broker_connection_lost", since.isoformat()
