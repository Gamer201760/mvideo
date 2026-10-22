import traceback
import urllib.request
from copy import deepcopy
from typing import Any

import pytest

from app.adapter.llm.output_validation import validate_output
from app.domain.errors import InvalidModelOutput
from app.domain.inference import JsonSchema
from app.usecase.attribute_flow_contract import SCHEMA

VALID: dict[str, Any] = {
    "c": [
        {"i": 0, "k": 0, "a": [{"f": 0, "v": "красный", "u": "", "q": "красный", "r": 0}], "r": []}
    ]
}


@pytest.mark.parametrize("category", [0, "Техника / Чайники", None])
@pytest.mark.parametrize("field", [0, "Цвет корпуса"])
@pytest.mark.parametrize("risk", [0, 7])
def test_real_production_output_supports_all_declared_union_branches(
    category: int | str | None, field: int | str, risk: int
) -> None:
    output = deepcopy(VALID)
    output["c"][0]["k"] = category
    output["c"][0]["a"][0].update(f=field, r=risk)
    unchanged = deepcopy(output)
    validate_output(output, SCHEMA)
    assert output == unchanged


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("c",), {}),
        (("c", 0), []),
        (("c", 0, "i"), True),
        (("c", 0, "i"), "0"),
        (("c", 0, "k"), False),
        (("c", 0, "k"), {}),
        (("c", 0, "a"), {}),
        (("c", 0, "a", 0), []),
        (("c", 0, "a", 0, "f"), True),
        (("c", 0, "a", 0, "f"), None),
        (("c", 0, "a", 0, "v"), 7),
        (("c", 0, "a", 0, "u"), None),
        (("c", 0, "a", 0, "q"), ["красный"]),
        (("c", 0, "a", 0, "r"), -1),
        (("c", 0, "a", 0, "r"), 8),
        (("c", 0, "a", 0, "r"), True),
        (("c", 0, "a", 0, "r"), 1.5),
        (("c", 0, "r"), [False]),
        (("c", 0, "r"), ["0"]),
    ],
)
def test_production_schema_rejects_nested_type_and_range_violations(
    path: tuple[str | int, ...], replacement: Any
) -> None:
    output = deepcopy(VALID)
    parent: Any = output
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = replacement
    with pytest.raises(InvalidModelOutput):
        validate_output(output, SCHEMA)


@pytest.mark.parametrize("level", ["root", "card", "answer"])
def test_additional_properties_are_rejected_at_every_production_level(level: str) -> None:
    output = deepcopy(VALID)
    target = output if level == "root" else output["c"][0]
    if level == "answer":
        target = target["a"][0]
    target["private-extension"] = "private model data"
    with pytest.raises(InvalidModelOutput):
        validate_output(output, SCHEMA)


@pytest.mark.parametrize("key", ["c", "i", "k", "a", "r", "f", "v", "u", "q", "answer-risk"])
def test_required_properties_are_enforced_through_nested_arrays(key: str) -> None:
    output = deepcopy(VALID)
    if key == "c":
        del output["c"]
    elif key in {"i", "k", "a", "r"}:
        del output["c"][0][key]
    else:
        del output["c"][0]["a"][0]["r" if key == "answer-risk" else key]
    with pytest.raises(InvalidModelOutput):
        validate_output(output, SCHEMA)


@pytest.mark.parametrize(
    ("rule", "invalid", "valid"),
    [
        ({"enum": ["red", "blue"]}, "green", "red"),
        ({"const": "red"}, "blue", "red"),
        ({"type": "string", "minLength": 2, "maxLength": 3}, "r", "red"),
        ({"type": "string", "pattern": "^[A-Z]+$"}, "red", "RED"),
        ({"type": "string", "format": "email"}, "invalid-email", "a@example.test"),
        ({"type": "number", "minimum": 1, "maximum": 3}, 4, 3),
        ({"type": "number", "exclusiveMinimum": 1, "exclusiveMaximum": 3}, 3, 2),
        ({"type": "number", "multipleOf": 2}, 3, 4),
        ({"type": "array", "minItems": 1, "maxItems": 2}, [], [1]),
        ({"type": "array", "uniqueItems": True}, [1, 1], [1, 2]),
        ({"type": "array", "items": {"type": "integer"}}, [True], [1]),
        ({"anyOf": [{"type": "integer"}, {"const": "unknown"}]}, True, "unknown"),
        ({"oneOf": [{"type": "integer"}, {"minimum": 0}]}, 1, -1),
        ({"allOf": [{"type": "integer"}, {"minimum": 0}]}, -1, 0),
        ({"not": {"type": "integer"}}, 1, "red"),
    ],
)
def test_validation_enforces_constraints_beyond_hand_written_field_checks(
    rule: JsonSchema, invalid: Any, valid: Any
) -> None:
    schema = {"type": "object", "properties": {"v": rule}, "required": ["v"]}
    validate_output({"v": valid}, schema)
    with pytest.raises(InvalidModelOutput):
        validate_output({"v": invalid}, schema)


def test_local_schema_references_are_supported() -> None:
    schema: JsonSchema = {
        "$defs": {"risk": {"type": "integer", "minimum": 0, "maximum": 7}},
        "type": "object",
        "properties": {"risk": {"$ref": "#/$defs/risk"}},
    }
    validate_output({"risk": 7}, schema)
    with pytest.raises(InvalidModelOutput):
        validate_output({"risk": 8}, schema)


@pytest.mark.parametrize("uri", ["https://private.example/token", "file:///private/schema.json"])
def test_external_references_cannot_fetch_network_or_files(
    monkeypatch: pytest.MonkeyPatch, uri: str
) -> None:
    def unexpected_fetch(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Schema references must stay offline")

    monkeypatch.setattr(urllib.request, "urlopen", unexpected_fetch)
    with pytest.raises(InvalidModelOutput) as error:
        validate_output({"private": "response"}, {"$ref": uri})
    assert uri not in "".join(traceback.format_exception(error.value))


@pytest.mark.parametrize("schema", [{"type": "private-invalid-type"}, {"required": "private"}])
def test_invalid_schema_and_output_details_never_escape_safe_error(schema: JsonSchema) -> None:
    output = {"private-response": "secret"}
    with pytest.raises(InvalidModelOutput) as error:
        validate_output(output, schema)
    rendered = "".join(traceback.format_exception(error.value))
    assert "secret" not in rendered
    assert "private-invalid-type" not in rendered
    assert "private-response" not in rendered
    assert str(error.value) == InvalidModelOutput.message


def test_validation_error_does_not_expose_private_response_or_schema() -> None:
    output = {"private-response": "private-value"}
    schema = {"const": {"private-schema": 1}}
    with pytest.raises(InvalidModelOutput) as error:
        validate_output(output, schema)
    rendered = "".join(traceback.format_exception(error.value))
    assert "private-value" not in rendered
    assert "private-schema" not in rendered


def test_draft_identifier_selects_the_requested_schema_dialect() -> None:
    schema = {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "type": "object",
        "properties": {"v": {"type": "number", "minimum": 0, "exclusiveMinimum": True}},
    }
    validate_output({"v": 1}, schema)
    with pytest.raises(InvalidModelOutput):
        validate_output({"v": 0}, schema)
