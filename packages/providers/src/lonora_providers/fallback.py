from lonora_core.user_error import LonoraError


def may_fallback(error: LonoraError) -> bool:
    return error.code in {
        "model_provider_unavailable",
        "model_rate_limited",
        "model_endpoint_unavailable",
    }
