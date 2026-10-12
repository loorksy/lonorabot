def normalize_retcode(code: str | int | None) -> str:
    value = str(code or "unknown")
    if value in {"TRADE_RETCODE_DONE", "TRADE_RETCODE_PLACED", "10009", "10008"}:
        return "confirmed"
    if value in {"TRADE_RETCODE_TIMEOUT", "10012", "unknown"}:
        return "ambiguous"
    return "failed"
