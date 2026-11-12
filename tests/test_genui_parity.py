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
from lonora_contracts.genui import ACTIONS, COMMON, NODES, SERVER_NODES, walk

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from scripts.export_genui_catalog import TARGET, generated  # noqa: E402
from test_genui_projector import messages, project, reply  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures/genui"
PARITY = (FIXTURES / "documents/valid/parity.lonora-ui").read_text()
COMPILED = FIXTURES / "parity-compiled.json"
OWNER = "احسب حجم الصفقة لرصيد 10000 كما في https://example.com/position-size"


async def compiled_documents() -> list[dict[str, Any]]:
    """The parity calculator and the A01 alert (the server's delivery row), as stored."""
    documents: list[dict[str, Any]] = []
    history = [ModelMessage(role="user", content=OWNER)]
    for text, past in ((reply(PARITY), history), (reply(), messages())):
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
    assert set(COMMON) == {"when"} and "every node takes when?" in vocabulary
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
