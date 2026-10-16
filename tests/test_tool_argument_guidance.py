import json

import pytest
from lonora_contracts.domain import Contract
from lonora_tools.schema import ToolArgumentsError, validate_arguments


class PrivateInput(Contract):
    count: int


def test_validation_guidance_never_returns_submitted_secret_or_validator_context():
    secret = "private-value-that-must-not-enter-the-tool-result"
    with pytest.raises(ToolArgumentsError) as caught:
        validate_arguments(PrivateInput, {"count": secret})
    assert caught.value.code == "tool_arguments_invalid"
    assert caught.value.issues == [{"path": ["count"], "type": "int_parsing"}]
    assert secret not in json.dumps(caught.value.issues)
