from lonora_core.user_error import LonoraError


def check_account_delegation(account_id: str, allowed_accounts: set[str] | None) -> None:
    if allowed_accounts is not None and account_id not in allowed_accounts:
        raise LonoraError("account_delegation_forbidden", 403)
