"""Schema labels must not crowd out context or erase real title properties."""

from typing import Any, Literal

import pytest
from jsonschema import Draft202012Validator, validate
from jsonschema.exceptions import ValidationError
from lonora_contracts.domain import Contract
from lonora_tools.schema import compact_input_schema
from pydantic import Field


class Annotation(Contract):
    title: str = Field(min_length=3, max_length=20)
    kind: Literal["level", "region"]


class Drawing(Contract):
    title: str = Field(min_length=1)
    annotations: list[Annotation] = Field(min_length=1, max_length=3)
    optional_note: str | None = None


@pytest.mark.parametrize(
    "value,valid",
    [
        ({"title": "Analysis", "annotations": [{"title": "Zone", "kind": "level"}]}, True),
        (
            {
                "title": "Analysis",
                "annotations": [{"title": "Zone", "kind": "region"}],
                "optional_note": None,
            },
            True,
        ),
        ({"title": "Analysis", "annotations": []}, False),
        ({"annotations": [{"title": "Zone", "kind": "level"}]}, False),
        ({"title": "Analysis", "annotations": [{"title": "X", "kind": "level"}]}, False),
        ({"title": "Analysis", "annotations": [{"title": "Zone", "kind": "unknown"}]}, False),
        (
            {"title": "Analysis", "annotations": [{"title": "Zone", "kind": "level", "extra": 1}]},
            False,
        ),
        (
            {"title": "Analysis", "annotations": [{"title": "Zone", "kind": "level"}], "extra": 1},
            False,
        ),
    ],
)
def test_real_named_properties_and_nested_validation_are_preserved(value: Any, valid: bool) -> None:
    original = Drawing.model_json_schema()
    compact = compact_input_schema(original)
    for schema in (original, compact):
        if valid:
            validate(value, schema, cls=Draft202012Validator)
        else:
            with pytest.raises(ValidationError):
                validate(value, schema, cls=Draft202012Validator)
    assert compact["properties"]["title"]["minLength"] == 1
    assert compact["$defs"]["Annotation"]["properties"]["title"]["minLength"] == 3
    assert original["title"] == "Drawing"  # No caller mutation.


def test_annotation_values_and_property_maps_are_not_schema_metadata() -> None:
    source = {
        "title": "Redundant label",
        "type": "object",
        "description": "Keep useful argument guidance.",
        "properties": {"title": {"type": "string", "title": "Label"}},
        "default": {"title": "A real default value"},
    }
    compact = compact_input_schema(source)
    assert compact["description"] == source["description"]
    assert compact["default"] == source["default"]
    assert "title" in compact["properties"]
    assert compact["properties"]["title"] == {"type": "string"}
