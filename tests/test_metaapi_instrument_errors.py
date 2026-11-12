"""An instrument the broker does not list is reported as such, not as a missing account."""

import pytest
from lonora_adapters.brokers.metaapi import provider_error


class ProviderFailure(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


@pytest.mark.parametrize("stage", ["symbol", "instrument"])
def test_a_symbol_read_404_is_symbol_not_found(stage: str) -> None:
    assert provider_error(ProviderFailure("Symbol XYZ not found", 404), stage).code == (
        "symbol_not_found"
    )
    assert provider_error(ProviderFailure("Not found", 404), stage).code == "symbol_not_found"


@pytest.mark.parametrize("stage", ["symbol", "instrument"])
def test_a_missing_account_stays_the_account(stage: str) -> None:
    error = ProviderFailure("Trading account not found", 404)
    assert provider_error(error, stage).code == "broker_account_not_found"


def test_other_stages_are_unchanged() -> None:
    assert provider_error(ProviderFailure("Not found", 404), "account").code == (
        "broker_account_not_found"
    )
    assert provider_error(ProviderFailure("Too many", 429), "instrument").code == (
        "broker_rate_limited"
    )
