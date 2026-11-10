"""The generated vocabulary of the v2 prompt block (GENUI_PLAN §9.5), built from the live
registries so it can never drift from what the compiler accepts: the S-A01 node set and its
props, the functions, the actions, the intents with their data, the icon names and the
instrument name table. Deterministic, so the block stays in the cached prompt prefix."""

from lonora_contracts.genui import COMMON, NODES, SLICE_NODES
from lonora_contracts.genui_functions import FUNCTIONS
from lonora_contracts.genui_icons import ICON_NAMES
from lonora_contracts.instrument_names import vocabulary_line

NODE_ORDER = ("Segmented", "Number", "Text", "Note", "KeyValue", "Button", "Row", "More", "Divider")


def _node(name: str) -> str:
    spec = NODES[name]
    props = [key + ("" if required else "?") for key, (required, _check) in spec.items()]
    return f"{name}{{{', '.join(props)}}}"


def genui_vocabulary() -> str:
    assert set(NODE_ORDER) == SLICE_NODES and set(COMMON) == {"when"}
    functions = ", ".join(sorted(name for name in FUNCTIONS if name != "Fact"))
    return "\n".join(
        [
            "Nodes (every node takes when?): " + " · ".join(_node(n) for n in NODE_ORDER),
            "Options: a list of {value, label?, also?{key: value}}; also is merged into state when picked.",
            "Text tone: info, good, warn, bad, muted, accent; size: sm. Button style: primary or outline; full: true.",
            "Actions (Button.action): {do:send, intent, data{field: $key or literal}, lock?} · {do:go, route} · {do:set, key, value} · {do:toggle, key} · {do:reset}. A Button with no action sends its label as the owner's question (intent ask).",
            "Intents: alert.create data {symbol: $key of a Segmented of quoted symbols, dir: above|below, price: $key} (Lonora adds the account and the delivery row) · alert.off data {watch_id: the id from watch_create or watch_list}.",
            "Functions: @Fact('key') (a data-line fact), " + functions + ".",
            "Icons: " + ", ".join(sorted(ICON_NAMES)) + ".",
            "Instrument names (label asset options with these): " + vocabulary_line() + ".",
        ]
    )
