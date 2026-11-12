"""The generated vocabulary of the v2 prompt block (GENUI_PLAN §9.5), built from the live
registries so it can never drift from what the compiler accepts: the whole node set of the
contract (mandate 10.1.5) and its props, the functions, the actions, the intents with their
data, the icon names and the instrument name table. Deterministic, so the block stays in the
cached prompt prefix."""

from lonora_contracts.genui import ACTIONS, COMMON, NODES
from lonora_contracts.genui_functions import FUNCTIONS
from lonora_contracts.genui_icons import ICON_NAMES
from lonora_contracts.instrument_names import vocabulary_line

NODE_ORDER = (
    "Segmented",
    "Select",
    "Number",
    "Slider",
    "Title",
    "Text",
    "Markdown",
    "Note",
    "Badge",
    "KeyValue",
    "Stat",
    "Button",
    "Row",
    "Col",
    "Grid",
    "Card",
    "More",
    "Divider",
)


def _node(name: str) -> str:
    spec = NODES[name]
    props = [key + ("" if required else "?") for key, (required, _check) in spec.items()]
    return f"{name}{{{', '.join(props)}}}"


def genui_vocabulary() -> str:
    assert set(NODE_ORDER) == set(NODES) and set(COMMON) == {"when"}
    assert {"send", "go", "set", "toggle", "reset", "copy", "open"} == set(ACTIONS)
    functions = ", ".join(sorted(name for name in FUNCTIONS if name != "Fact"))
    return "\n".join(
        [
            "Nodes (every node takes when?): " + " · ".join(_node(n) for n in NODE_ORDER),
            "Options: a list of {value, label?, also?{key: value}}; also is merged into state when picked.",
            "Segmented for 2-4 options, Select for 5-20. Slider min, max, step: numbers; show: a template for its readout. Grid cols: 1, 2 or 3. Card: an inner panel with an optional title. Markdown: a short Markdown passage. Stat trend: an expression giving 'up' or 'down'.",
            "tone (Text, Note, Badge, Stat): info, good, warn, bad, muted, accent; Text size: sm. Button style: primary or outline; full: true.",
            "Actions (Button.action): {do:send, intent, data{field: $key or literal}, lock?} · {do:go, route} · {do:set, key, value} · {do:toggle, key} · {do:reset} · {do:copy, text} · {do:open, url: a literal https URL}. A Button with no action sends its label as the owner's question (intent ask).",
            "Intents: alert.create data {symbol: $key of a Segmented of quoted symbols, dir: above|below, price: $key} (Lonora adds the account and the delivery row) · alert.off data {watch_id: the id from watch_create or watch_list}.",
            "Functions: @Fact('key') (a data-line fact), " + functions + ".",
            "Icons: " + ", ".join(sorted(ICON_NAMES)) + ".",
            "Instrument names (label an asset option with its name in the owner's language): "
            + vocabulary_line()
            + ".",
        ]
    )
