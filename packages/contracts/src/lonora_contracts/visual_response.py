"""Versioned native composition, shared by ordinary Agent replies and both clients."""

import math
import re
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, JsonValue, field_validator, model_validator
from pydantic_core import PydanticCustomError

from .domain import Contract
from .visual_values import EXTENDED_ARITY, has_visual_placeholder, legacy_visual_bindings

MAX_VISUAL_BYTES = 64000
MAX_VISUAL_NODES = 120
MAX_VISUAL_DEPTH = 10
MAX_VISUAL_EXPRESSION_DEPTH = 8
NodeKind = Literal[
    "column",
    "row",
    "grid",
    "card",
    "container",
    "divider",
    "text",
    "heading",
    "badge",
    "icon",
    "metric",
    "table",
    "list",
    "progress",
    "timeline",
    "diagram",
    "chart",
    "image",
    "disclosure",
    "tabs",
    "button",
    "select",
    "checkbox",
    "slider",
    "input",
    "form",
]
Scalar = str | int | float | bool | None
KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,47}$")
RESERVED = {"__proto__", "prototype", "constructor"}
OPERATOR_ARITY: dict[str, tuple[int, int]] = {
    "add": (1, 8),
    "sub": (2, 2),
    "mul": (1, 8),
    "div": (2, 2),
    "min": (1, 8),
    "max": (1, 8),
    "round": (1, 2),
    "abs": (1, 1),
    "eq": (2, 2),
    "gt": (2, 2),
    "gte": (2, 2),
    "lt": (2, 2),
    "lte": (2, 2),
    "and": (1, 8),
    "or": (1, 8),
    "not": (1, 1),
    "if": (3, 3),
    **EXTENDED_ARITY,
}
OPERATORS = frozenset(OPERATOR_ARITY)


def _display(value: str | None) -> str | None:
    if value is not None and has_visual_placeholder(value):
        raise ValueError("visual_display_binding_unresolved")
    return value


class VisualAction(Contract):
    kind: Literal["follow_up", "open_chart", "open_artifact"]
    text: str | None = Field(default=None, max_length=2000)
    resource_id: str | None = Field(default=None, max_length=36)

    @model_validator(mode="after")
    def shape(self) -> Self:
        if self.kind == "follow_up":
            if not self.text or not self.text.strip() or self.resource_id is not None:
                raise ValueError("visual_action_invalid")
        else:
            if not self.resource_id or self.text is not None:
                raise ValueError("visual_action_invalid")
            if str(UUID(self.resource_id)).lower() != self.resource_id.lower():
                raise ValueError("visual_resource_invalid")
        return self


class VisualChoice(Contract):
    value: str = Field(max_length=100)
    label: str = Field(max_length=160)
    _label_display = field_validator("label")(_display)


class VisualField(Contract):
    key: str = Field(pattern=KEY.pattern)
    label: str = Field(max_length=160)
    _label_display = field_validator("label")(_display)


class DiagramVertex(Contract):
    id: str = Field(pattern=KEY.pattern)
    label: str = Field(max_length=160)
    _label_display = field_validator("label")(_display)


class DiagramEdge(Contract):
    source: str = Field(pattern=KEY.pattern)
    target: str = Field(pattern=KEY.pattern)
    label: str = Field(default="", max_length=100)
    _label_display = field_validator("label")(_display)


# Only these properties can be supplied for each trusted component. No arbitrary
# styles, HTML, JavaScript, URL handlers or model-invented action names exist.
COMMON = frozenset({"id", "type", "visible", "tone"})
ALLOWED: dict[str, set[str]] = {
    **{
        name: {"children", "label", "gap"}
        for name in ["column", "row", "container", "card", "list", "timeline", "disclosure", "form"]
    },
    "grid": {"children", "columns", "gap"},
    "divider": set(),
    "text": {"text", "value"},
    "heading": {"text", "level"},
    "badge": {"text", "value"},
    "icon": {"text"},
    "metric": {"label", "value", "unit"},
    "table": {"label", "fields", "rows", "filter_key"},
    "progress": {"label", "value", "maximum"},
    "diagram": {"label", "vertices", "edges"},
    "chart": {"label", "chart_kind", "points"},
    "image": {"artifact_id", "label"},
    "tabs": {"children", "options", "state_key"},
    "button": {"label", "action"},
    "select": {"label", "options", "state_key"},
    "checkbox": {"label", "state_key"},
    "slider": {"label", "state_key", "minimum", "maximum", "step"},
    "input": {"label", "state_key", "input_kind", "minimum", "maximum", "step"},
}


class VisualNode(Contract):
    id: str = Field(pattern=KEY.pattern)
    type: NodeKind
    children: list["VisualNode"] = Field(default_factory=list["VisualNode"], max_length=40)
    text: str | None = Field(default=None, max_length=4000)
    label: str | None = Field(default=None, max_length=300)
    value: JsonValue = None
    unit: JsonValue = None
    visible: JsonValue = True
    tone: Literal["neutral", "info", "success", "warning", "danger"] = "neutral"
    gap: Literal["small", "normal", "large"] = "normal"
    level: int = Field(default=2, ge=1, le=4)
    columns: int = Field(default=2, ge=1, le=3)
    fields: list[VisualField] = Field(default_factory=list[VisualField], max_length=12)
    rows: list[dict[str, JsonValue]] = Field(
        default_factory=list[dict[str, JsonValue]], max_length=100
    )
    filter_key: str | None = Field(default=None, pattern=KEY.pattern)
    chart_kind: Literal["line", "bar", "pie"] = "line"
    points: list[dict[str, JsonValue]] = Field(
        default_factory=list[dict[str, JsonValue]], max_length=100
    )
    vertices: list[DiagramVertex] = Field(default_factory=list[DiagramVertex], max_length=20)
    edges: list[DiagramEdge] = Field(default_factory=list[DiagramEdge], max_length=30)
    options: list[VisualChoice] = Field(default_factory=list[VisualChoice], max_length=20)
    state_key: str | None = Field(default=None, pattern=KEY.pattern)
    minimum: float = 0
    maximum: float = 100
    step: float = Field(default=1, gt=0)
    input_kind: Literal["text", "number"] = "text"
    artifact_id: str | None = Field(default=None, max_length=36)
    action: VisualAction | None = None
    _text_display = field_validator("text", "label")(_display)

    @model_validator(mode="after")
    def properties(self) -> Self:
        if (
            self.id in RESERVED
            or any(field.key in RESERVED for field in self.fields)
            or any(vertex.id in RESERVED for vertex in self.vertices)
        ):
            raise ValueError("visual_key_invalid")
        if self.model_fields_set - COMMON - ALLOWED[self.type]:
            raise ValueError("visual_property_unsupported")
        if self.type in {"metric", "progress"} and "value" not in self.model_fields_set:
            raise ValueError("visual_value_required")
        if self.type in {"button"} and (not self.label or self.action is None):
            raise ValueError("visual_action_required")
        if self.type == "image" and not self.artifact_id:
            raise ValueError("visual_image_reference_required")
        if self.artifact_id:
            if str(UUID(self.artifact_id)).lower() != self.artifact_id.lower():
                raise ValueError("visual_resource_invalid")
        if self.type in {"select", "checkbox", "slider", "input", "tabs"} and not self.state_key:
            raise ValueError("visual_state_required")
        if self.type in {"select", "tabs"} and not self.options:
            raise ValueError("visual_options_required")
        if self.type == "tabs" and len(self.options) != len(self.children):
            raise ValueError("visual_tabs_invalid")
        if len({option.value for option in self.options}) != len(self.options):
            raise ValueError("visual_options_invalid")
        if len({field.key for field in self.fields}) != len(self.fields):
            raise ValueError("visual_table_invalid")
        if self.maximum < self.minimum or not all(
            math.isfinite(v) for v in [self.minimum, self.maximum, self.step]
        ):
            raise ValueError("visual_bounds_invalid")
        if self.type == "table" and (
            not self.fields or any(set(row) - {c.key for c in self.fields} for row in self.rows)
        ):
            raise ValueError("visual_table_invalid")
        if any(set(point) != {"label", "value"} for point in self.points):
            raise ValueError("visual_chart_invalid")
        identities = {vertex.id for vertex in self.vertices}
        if len(identities) != len(self.vertices) or any(
            edge.source not in identities or edge.target not in identities for edge in self.edges
        ):
            raise ValueError("visual_diagram_invalid")
        return self


class VisualFact(Contract):
    value: str | int | float | bool | None
    source: str = Field(max_length=100)
    observed_at: str | None = Field(default=None, max_length=80)


class VisualDocument(Contract):
    version: Literal[1] = 1
    mode: Literal["observed", "example", "estimate"]
    root: VisualNode
    state: dict[str, str | int | float | bool | None] = Field(default_factory=dict, max_length=20)
    facts: dict[str, VisualFact] = Field(default_factory=dict, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def legacy_bindings(cls, value: object) -> object:
        return legacy_visual_bindings(value)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if any(not KEY.fullmatch(key) or key in RESERVED for key in self.state):
            raise ValueError("visual_state_invalid")
        if len(self.model_dump_json(exclude_unset=True).encode()) > MAX_VISUAL_BYTES:
            raise ValueError("visual_document_too_large")
        if any(
            isinstance(value, float) and not math.isfinite(value) for value in self.state.values()
        ):
            raise ValueError("visual_number_invalid")
        if any(
            isinstance(value, str) and has_visual_placeholder(value)
            for value in self.state.values()
        ):
            raise ValueError("visual_display_binding_unresolved")
        if any(
            not KEY.fullmatch(key)
            or key in RESERVED
            or (isinstance(fact.value, float) and not math.isfinite(fact.value))
            for key, fact in self.facts.items()
        ):
            raise ValueError("visual_fact_invalid")
        if any(
            isinstance(fact.value, str) and has_visual_placeholder(fact.value)
            for fact in self.facts.values()
        ):
            raise ValueError("visual_display_binding_unresolved")
        seen: set[str] = set()

        def walk(node: VisualNode, depth: int, path: str = "root") -> None:
            if depth > MAX_VISUAL_DEPTH or node.id in seen or len(seen) >= MAX_VISUAL_NODES:
                raise PydanticCustomError(
                    "visual_tree_invalid", "Invalid visual tree", {"visual_path": path}
                )
            seen.add(node.id)
            if any(key and key not in self.state for key in [node.state_key, node.filter_key]):
                raise ValueError("visual_state_unknown")
            initial = self.state.get(node.state_key or "")
            if node.type in {"select", "tabs"} and initial not in {
                choice.value for choice in node.options
            }:
                raise ValueError("visual_state_initial_invalid")
            if node.type == "checkbox" and not isinstance(initial, bool):
                raise ValueError("visual_state_initial_invalid")
            if node.type == "slider" or (node.type == "input" and node.input_kind == "number"):
                if (
                    isinstance(initial, bool)
                    or not isinstance(initial, int | float)
                    or not (node.minimum <= initial <= node.maximum)
                ):
                    raise ValueError("visual_state_initial_invalid")
            if (node.type == "input" and node.input_kind == "text") and not isinstance(
                initial, str
            ):
                raise ValueError("visual_state_initial_invalid")
            if node.filter_key and not isinstance(self.state[node.filter_key], str):
                raise ValueError("visual_filter_invalid")
            if node.action and node.action.kind == "follow_up":

                def substitute(match: re.Match[str]) -> str:
                    key = match[1]
                    if key not in self.state or key in RESERVED:
                        raise ValueError("visual_action_state_unknown")
                    return ""

                template = re.sub(r"\{\{([^{}]+)\}\}", substitute, node.action.text or "")
                if "{{" in template or "}}" in template:
                    raise ValueError("visual_action_template_invalid")
            values = [
                (path + "." + field, getattr(node, field)) for field in ["value", "unit", "visible"]
            ]
            values.extend(
                (f"{path}.rows.{row_index}.cells.{cell_index}", value)
                for row_index, row in enumerate(node.rows)
                for cell_index, value in enumerate(row.values())
            )
            values.extend(
                (f"{path}.points.{index}.{field}", point[field])
                for index, point in enumerate(node.points)
                for field in ["label", "value"]
            )
            for value_path, value in values:
                validate_value(value, set(self.state), set(self.facts), path=value_path)
            for index, child in enumerate(node.children):
                walk(child, depth + 1, f"{path}.children.{index}")

        walk(self.root, 0)
        return self


def validate_value(
    value: JsonValue, state_keys: set[str], fact_keys: set[str], depth: int = 0, path: str = "value"
) -> None:
    try:
        _validate_value(value, state_keys, fact_keys, depth, path)
    except PydanticCustomError:
        raise
    except ValueError:
        raise PydanticCustomError(
            "visual_expression_invalid", "Invalid visual expression", {"visual_path": path}
        ) from None


def _validate_value(
    value: JsonValue, state_keys: set[str], fact_keys: set[str], depth: int, path: str
) -> None:
    if depth > MAX_VISUAL_EXPRESSION_DEPTH:
        raise ValueError("visual_expression_too_deep")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("visual_number_invalid")
    if value is None or isinstance(value, str | int | float | bool):
        if isinstance(value, str) and has_visual_placeholder(value):
            raise ValueError("visual_display_binding_unresolved")
        return
    if not isinstance(value, dict):
        raise ValueError("visual_expression_invalid")
    if set(value) == {"state"} and isinstance(value["state"], str) and value["state"] in state_keys:
        return
    if (
        set(value) == {"source"}
        and isinstance(value["source"], str)
        and value["source"] in fact_keys
    ):
        return
    if set(value) == {"fact"} and isinstance(value["fact"], dict):
        fact = value["fact"]
        if (
            set(fact) == {"call_id", "path"}
            and isinstance(fact["call_id"], str)
            and isinstance(fact["path"], str)
            and 0 < len(fact["call_id"]) <= 200
            and len(fact["path"]) <= 300
            and (not fact["path"] or fact["path"].startswith("/"))
        ):
            return
    if (
        set(value) == {"op", "args"}
        and isinstance(value["op"], str)
        and value["op"] in OPERATORS
        and isinstance(value["args"], list)
        and 1 <= len(value["args"]) <= 8
    ):
        arity = len(value["args"])
        op = value["op"]
        if not OPERATOR_ARITY[op][0] <= arity <= OPERATOR_ARITY[op][1]:
            raise ValueError("visual_operator_arity")
        for index, item in enumerate(value["args"]):
            validate_value(item, state_keys, fact_keys, depth + 1, f"{path}.args.{index}")
        return
    raise ValueError("visual_expression_invalid")


class RichTextPart(Contract):
    type: Literal["text"]
    text: str = Field(max_length=32000)


class RichUiPart(Contract):
    type: Literal["ui"]
    document: VisualDocument


class RichContent(Contract):
    version: Literal[1] = 1
    parts: list[RichTextPart | RichUiPart] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def compiled(self) -> Self:
        if len(self.model_dump_json(exclude_unset=True).encode()) > 128000:
            raise ValueError("visual_response_too_large")

        def resolved(value: JsonValue) -> None:
            if isinstance(value, dict):
                if set(value) == {"fact"} and isinstance(value["fact"], dict):
                    raise ValueError("visual_fact_unresolved")
                for item in value.values():
                    resolved(item)
            elif isinstance(value, list):
                for item in value:
                    resolved(item)

        for part in self.parts:
            if isinstance(part, RichUiPart):
                resolved(part.document.model_dump(mode="json", exclude_unset=True))
        return self
