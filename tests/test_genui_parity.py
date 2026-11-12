"""One v2 component set (mandate 10.1.5): the server contract, the vocabulary taught to the
model, the client validator and both renderers accept the same nodes and actions.

The contract is the source of truth. This file checks the contract against the vocabulary
and the generated client catalog, and compiles the parity cards (every node and every
action) through the real projector into ``tests/fixtures/genui/parity-compiled.json``, the
documents the client checks render: ``tests/web/genui-parity.test.ts`` (the client
validator), ``pnpm check`` (both renderers type their node map against the catalog) and the
web and Expo ``genui.spec.mjs`` journeys (each renderer draws every node type).

Run ``.venv/bin/python tests/test_genui_parity.py`` to rewrite the compiled fixture.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from lonora_adapter_kit.types import ModelMessage
from unittest.mock import patch

from lonora_contracts.genui import ACTIONS, COMMON, NODES, SERVER_NODES, SLOT, node_props, walk

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from test_genui_projector import messages, project, reply  # noqa: E402

from scripts.export_genui_catalog import TARGET, generated  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures/genui"
PARITY = (FIXTURES / "documents/valid/parity.lonora-ui").read_text()
SLOTS = (FIXTURES / "documents/valid/slot.lonora-ui").read_text()
# The same card with the other fixed card that exists today (two slots exceed 560 px).
SETTLE = SLOTS.replace(
    '"trade_approval","record":"parity-approval"', '"settle","record":"parity-settle"'
)
# The records the slot card names, as ``lonora_db.genui_slots`` finds them in this
# conversation (tests/test_genui_slots.py checks the lookup against real rows).
SLOT_RECORDS = {("trade_approval", "parity-approval"), ("settle", "parity-settle")}
COMPILED = FIXTURES / "parity-compiled.json"
OWNER = "احسب حجم الصفقة لرصيد 10000 كما في https://example.com/position-size"


async def compiled_documents() -> list[dict[str, Any]]:
    """The parity calculator, the A01 alert (the server's delivery row) and the trusted
    slots of both fixed cards that exist, as stored."""
    documents: list[dict[str, Any]] = []
    history = [ModelMessage(role="user", content=OWNER)]

    async def records(*_args: Any) -> set[tuple[str, str]]:
        return SLOT_RECORDS

    for text, past in (
        (reply(PARITY), history),
        (reply(), messages()),
        (reply(SLOTS), history),
        (reply(SETTLE), history),
    ):
        with patch("lonora_agent.visual_response.slot_records", records):
            projection, projector = await project(text, history=past)
        assert not projector.diagnostics, projector.diagnostics
        rich = projection.rich_until()
        assert rich is not None
        documents.append(rich["parts"][1]["document"])
    return documents


def test_the_client_catalog_is_generated_from_the_contract() -> None:
    assert TARGET.read_text() == generated(), "run scripts/export_genui_catalog.py"


def test_the_vocabulary_teaches_every_node_prop_and_action() -> None:
    from lonora_agent.genui_vocabulary import genui_vocabulary

    vocabulary = genui_vocabulary()
    for name, spec in NODES.items():
        props = [key + ("" if required else "?") for key, (required, _c) in spec.items()]
        assert f"{name}{{{', '.join(props)}}}" in vocabulary
    for action in ACTIONS:
        assert f"{{do:{action}" in vocabulary
    assert set(COMMON) == {"when"} and f"every node but {SLOT} takes when?" in vocabulary
    # A slot takes no common prop: it can never be hidden (mandate 10.2.2).
    assert node_props(SLOT) == NODES[SLOT]
    for server in SERVER_NODES:
        assert server not in vocabulary  # written by the compiler, never by the model


def test_the_icon_catalog_is_the_icons_the_clients_draw() -> None:
    import re

    from lonora_contracts.genui_icons import ICON_NAMES

    source = (Path(__file__).parents[1] / "packages/ui-tokens/src/icons.ts").read_text()
    drawn = set(re.findall(r"^  ([A-Za-z]+):", source, re.M))
    assert drawn == set(ICON_NAMES)


@pytest.mark.asyncio
async def test_the_parity_cards_compile_cleanly_and_cover_the_whole_set() -> None:
    documents = await compiled_documents()
    types = {node["type"] for document in documents for _p, node in walk(document["blocks"])}
    assert types == set(NODES) | set(SERVER_NODES)
    actions = {
        node["action"]["do"]
        for document in documents
        for _p, node in walk(document["blocks"])
        if "action" in node
    }
    # A Button without an action sends its label (intent ask): the send is covered by A01.
    assert actions == set(ACTIONS)
    # Every prop of every node is exercised, so the journeys draw each one.
    used = {
        (node["type"], prop)
        for document in documents
        for _p, node in walk(document["blocks"])
        for prop in node
        if prop != "type"
    }
    expected = {(name, prop) for name, spec in NODES.items() for prop in spec}
    assert expected - used == set()
    # `when` (COMMON) is one generic rule in both renderers; it is exercised too.
    assert {prop for _type, prop in used} >= set(COMMON)
    assert json.loads(COMPILED.read_text()) == {"documents": documents}, (
        "run .venv/bin/python tests/test_genui_parity.py"
    )


if __name__ == "__main__":
    COMPILED.write_text(
        json.dumps({"documents": asyncio.run(compiled_documents())}, ensure_ascii=False, indent=2)
        + "\n"
    )
