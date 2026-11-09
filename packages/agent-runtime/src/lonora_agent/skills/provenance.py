"""Truthful origin labels for every skill the model sees.

The label follows the manifest source, which the server sets for packages:
an agent's workspace package is ``installed`` and a pinned GitHub import is
``external``. Only shipped definitions are first-party. A label describes where
instructions came from; none of them grants tools or financial authority.
"""

from typing import Literal

SkillProvenance = Literal["bundled", "owner", "agent_authored", "external", "unverified"]

PROVENANCE: dict[str, SkillProvenance] = {
    "builtin": "bundled",
    "owner": "owner",
    # Legacy skills are owner-API instructions saved before manifests existed.
    "legacy": "owner",
    "installed": "agent_authored",
    "external": "external",
}
# Context-section trust labels for active procedure bodies.
TRUST = {
    "bundled": "bundled_first_party",
    "owner": "owner_supplied",
    "agent_authored": "agent_authored",
    "external": "external_import",
    "unverified": "unverified_skill",
}
# Earlier releases labelled every non-builtin skill this way; stored skill_view
# receipts may still carry it.
LEGACY_LABEL = "owner_supplied"


def skill_provenance(source: str) -> SkillProvenance:
    return PROVENANCE.get(source, "unverified")


def skill_trust(source: str) -> str:
    if source == "legacy":
        return "legacy_owner_skill"
    return TRUST[skill_provenance(source)]
