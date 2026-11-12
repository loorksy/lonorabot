"""Regenerate the lonora-ui v2 component catalog for the clients from the server contract.

The server contract (``lonora_contracts.genui``) is the one source of truth for the v2
component set (mandate 10.1.5), and ``lonora_agent.genui_capabilities.ROUTES`` of the
routes a ``go`` action may name. This writes ``packages/contracts/src/genui-catalog.ts``,
which the client validator, the web renderer and the mobile renderer type against, so a
node or action the server accepts and a client does not render fails ``pnpm check`` and
``tests/web/genui-parity.test.ts``. Use --check during builds.
"""

import argparse
import json
from pathlib import Path

from lonora_agent.genui_capabilities import ROUTES
from lonora_contracts.genui import ACTIONS, NODES, SERVER_NODES, SLOT_CARDS, TONES, node_props

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "packages/contracts/src/genui-catalog.ts"


def _list(items: list[str] | tuple[str, ...], indent: str = "") -> str:
    """A string array as biome formats it (one line when it fits in 100 columns)."""
    flat = "[" + ", ".join(json.dumps(item) for item in items) + "]"
    if len(flat) <= 60:
        return flat
    return "[\n" + "".join(f"{indent}  {json.dumps(item)},\n" for item in items) + indent + "]"


def _props(name: str, spec: dict[str, bool]) -> str:
    """One catalog row as biome formats it (wrapped past 100 columns)."""
    pairs = [f"{key}: {str(value).lower()}" for key, value in spec.items()]
    flat = f"  {name}: {{ {', '.join(pairs)} }},\n"
    if len(flat) <= 101:
        return flat
    return f"  {name}: {{\n" + "".join(f"    {pair},\n" for pair in pairs) + "  },\n"


def generated() -> str:
    props = {
        name: {key: required for key, (required, _check) in node_props(name).items()}
        for name in NODES
    }
    nodes = _list(list(NODES))
    server = _list(SERVER_NODES)
    actions = _list(ACTIONS)
    routes = _list(ROUTES)
    rows = "".join(_props(name, spec) for name, spec in props.items())
    return (
        "/** The lonora-ui v2 component catalog (mandate 10.1.5), generated from the server\n"
        " * contract `lonora_contracts.genui` by `scripts/export_genui_catalog.py`. Do not edit:\n"
        " * the client validator and both renderers type against it, so they accept exactly\n"
        " * the node types and actions the server accepts. */\n"
        f"export const UI_NODE_TYPES = {nodes} as const;\n"
        "export type UiNodeType = (typeof UI_NODE_TYPES)[number];\n"
        "/** Rows only the server writes into a compiled card (never taught to the model). */\n"
        f"export const UI_SERVER_NODE_TYPES = {server} as const;\n"
        "export type UiServerNodeType = (typeof UI_SERVER_NODE_TYPES)[number];\n"
        "export type UiRenderedNodeType = UiNodeType | UiServerNodeType;\n"
        f"export const UI_ACTIONS = {actions} as const;\n"
        "export type UiActionKind = (typeof UI_ACTIONS)[number];\n"
        "/** The client routes a `go` action may name (`lonora_agent.genui_capabilities`). */\n"
        f"export const UI_ROUTES = {routes} as const;\n"
        "export type UiRoute = (typeof UI_ROUTES)[number];\n"
        f"export const UI_TONES = {_list(TONES)} as const;\n"
        "/** The fixed cards a Slot may place (mandate 10.2); the client draws them from the\n"
        " * live record. */\n"
        f"export const UI_SLOT_CARDS = {_list(SLOT_CARDS)} as const;\n"
        "export type UiSlotCard = (typeof UI_SLOT_CARDS)[number];\n"
        "export type UiTone = (typeof UI_TONES)[number];\n"
        "/** Each node's props: true when required. Each renderer declares that it draws every\n"
        " * one (`UiNodeProps`), so a prop the contract gains fails `pnpm check`. */\n"
        "export const UI_NODE_PROPS = {\n"
        f"{rows}}} as const satisfies Record<UiNodeType, Readonly<Record<string, boolean>>>;\n"
        "/** Every prop of every node, each marked as drawn by a renderer. */\n"
        "export type UiNodeProps = {\n"
        "  [Node in UiNodeType]: { [Prop in keyof (typeof UI_NODE_PROPS)[Node]]: true };\n"
        "};\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = generated()
    if args.check:
        if not TARGET.exists() or TARGET.read_text() != text:
            raise SystemExit(
                "genui-catalog.ts is stale: run .venv/bin/python scripts/export_genui_catalog.py"
            )
        return
    TARGET.write_text(text)


if __name__ == "__main__":
    main()
