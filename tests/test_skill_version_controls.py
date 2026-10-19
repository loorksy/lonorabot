"""Bounded denial configuration cannot admit malformed or duplicate identities."""

import pytest
from lonora_contracts.domain import utcnow
from lonora_contracts.skills import SkillRevokeRequest, SkillVersionControls, SkillVersionRevocation
from pydantic import ValidationError


@pytest.mark.parametrize(
    "changes",
    [
        {"skill_id": "../outside"},
        {"version": "latest"},
        {"version": "01.0.0"},
        {"version": "1" * 65 + ".0.0"},
        {"reason": "arbitrary_secret_prose"},
        {"expected_revision": -1},
        {"owner_id": "forged"},
    ],
)
def test_denial_request_has_exact_bounded_version_and_reason(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SkillRevokeRequest.model_validate(
            {"skill_id": "analysis", "version": "1.0.0", "expected_revision": 0, **changes}
        )


def test_controls_reject_duplicate_denials_and_false_revision() -> None:
    revocation = SkillVersionRevocation(skill_id="analysis", version="1.0.0", revoked_at=utcnow())
    for revision, items in ((2, [revocation, revocation]), (0, [revocation])):
        with pytest.raises(ValidationError):
            SkillVersionControls(
                owner_id="owner", agent_id="agent", revision=revision, revoked=items
            )
