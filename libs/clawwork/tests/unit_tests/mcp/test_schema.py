# ruff: noqa: PLR2004
# mypy: disable-error-code="attr-defined"
"""Tests for clawwork.mcp._schema — JSON Schema to Pydantic model conversion."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from clawwork.mcp._schema import json_schema_to_model


class TestSimpleTypes:
    """Test primitive JSON Schema type mapping."""

    def test_required_string_field(self) -> None:
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        model = json_schema_to_model("Test", schema)
        instance = model(name="hello")
        assert instance.name == "hello"

    def test_integer_field(self) -> None:
        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
        }
        model = json_schema_to_model("Test", schema)
        instance = model(count=42)
        assert instance.count == 42

    def test_number_field(self) -> None:
        schema = {
            "type": "object",
            "properties": {"score": {"type": "number"}},
            "required": ["score"],
        }
        model = json_schema_to_model("Test", schema)
        instance = model(score=3.14)
        assert instance.score == 3.14

    def test_boolean_field(self) -> None:
        schema = {
            "type": "object",
            "properties": {"flag": {"type": "boolean"}},
            "required": ["flag"],
        }
        model = json_schema_to_model("Test", schema)
        instance = model(flag=True)
        assert instance.flag is True


class TestOptionalFields:
    """Test required vs optional field handling."""

    def test_optional_field_defaults_to_none(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name"],
        }
        model = json_schema_to_model("Test", schema)
        instance = model(name="alice")
        assert instance.name == "alice"
        assert instance.age is None

    def test_required_field_missing_raises_validation_error(self) -> None:
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        model = json_schema_to_model("Test", schema)
        with pytest.raises(ValidationError):
            model()


class TestSchemaDefaults:
    """Test that JSON Schema default values are honored."""

    def test_schema_default_string(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "depth": {"type": "string", "default": "basic"},
            },
            "required": ["query"],
        }
        model = json_schema_to_model("Test", schema)
        instance = model(query="hello")
        assert instance.depth == "basic"

    def test_schema_default_integer(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 5},
            },
        }
        model = json_schema_to_model("Test", schema)
        instance = model()
        assert instance.limit == 5

    def test_schema_default_boolean(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "verbose": {"type": "boolean", "default": False},
            },
        }
        model = json_schema_to_model("Test", schema)
        instance = model()
        assert instance.verbose is False

    def test_schema_default_overridden_by_caller(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "depth": {"type": "string", "default": "basic"},
            },
        }
        model = json_schema_to_model("Test", schema)
        instance = model(depth="advanced")
        assert instance.depth == "advanced"

    def test_schema_default_not_nullable(self) -> None:
        """Fields with a non-None schema default should not accept None."""
        schema = {
            "type": "object",
            "properties": {
                "depth": {"type": "string", "default": "basic"},
            },
        }
        model = json_schema_to_model("Test", schema)
        with pytest.raises(ValidationError):
            model(depth=None)

    def test_schema_default_null_falls_back_to_nullable(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "tag": {"type": "string", "default": None},
            },
        }
        model = json_schema_to_model("Test", schema)
        instance = model()
        assert instance.tag is None

    def test_schema_default_excluded_when_unset(self) -> None:
        """Schema defaults should be excluded by model_dump(exclude_unset=True)."""
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "depth": {"type": "string", "default": "basic"},
            },
            "required": ["query"],
        }
        model = json_schema_to_model("Test", schema)
        instance = model(query="hello")
        dumped = instance.model_dump(exclude_unset=True)
        assert dumped == {"query": "hello"}

    def test_schema_default_included_when_explicitly_set(self) -> None:
        """Explicitly set fields should appear in model_dump(exclude_unset=True)."""
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "depth": {"type": "string", "default": "basic"},
            },
            "required": ["query"],
        }
        model = json_schema_to_model("Test", schema)
        instance = model(query="hello", depth="advanced")
        dumped = instance.model_dump(exclude_unset=True)
        assert dumped == {"query": "hello", "depth": "advanced"}


class TestArrays:
    """Test array type mapping."""

    def test_array_with_item_type(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["tags"],
        }
        model = json_schema_to_model("Test", schema)
        instance = model(tags=["a", "b"])
        assert instance.tags == ["a", "b"]

    def test_array_without_item_type(self) -> None:
        schema = {
            "type": "object",
            "properties": {"data": {"type": "array"}},
            "required": ["data"],
        }
        model = json_schema_to_model("Test", schema)
        instance = model(data=[1, "two", True])
        assert instance.data == [1, "two", True]


class TestNestedObjects:
    """Test nested object type mapping."""

    def test_nested_object_creates_submodel(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "config": {
                    "type": "object",
                    "properties": {
                        "host": {"type": "string"},
                        "port": {"type": "integer"},
                    },
                    "required": ["host"],
                },
            },
            "required": ["config"],
        }
        model = json_schema_to_model("Test", schema)
        instance = model(config={"host": "localhost", "port": 8080})
        assert instance.config.host == "localhost"
        assert instance.config.port == 8080

    def test_object_without_properties_becomes_dict(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "metadata": {"type": "object"},
            },
            "required": ["metadata"],
        }
        model = json_schema_to_model("Test", schema)
        instance = model(metadata={"key": "value"})
        assert instance.metadata == {"key": "value"}


class TestUnionAndEdgeCases:
    """Test anyOf, oneOf, nullable, and edge cases."""

    def test_anyof_becomes_any(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "value": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
            },
            "required": ["value"],
        }
        model = json_schema_to_model("Test", schema)
        assert model(value="hello").value == "hello"
        assert model(value=42).value == 42

    def test_nullable_type_array(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": ["string", "null"]},
            },
            "required": ["name"],
        }
        model = json_schema_to_model("Test", schema)
        assert model(name="alice").name == "alice"
        assert model(name=None).name is None

    def test_empty_schema_creates_empty_model(self) -> None:
        schema: dict[str, Any] = {"type": "object"}
        model = json_schema_to_model("Test", schema)
        instance = model()
        assert isinstance(instance, BaseModel)

    def test_missing_type_becomes_any(self) -> None:
        schema = {
            "type": "object",
            "properties": {"x": {}},
            "required": ["x"],
        }
        model = json_schema_to_model("Test", schema)
        assert model(x="anything").x == "anything"


class TestFieldDescription:
    """Test that field descriptions are preserved."""

    def test_description_on_field(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
            },
            "required": ["query"],
        }
        model = json_schema_to_model("Test", schema)
        field_info = model.model_fields["query"]
        assert field_info.description == "The search query"


class TestModelName:
    """Test that the generated model has the correct class name."""

    def test_model_name_matches_argument(self) -> None:
        schema = {
            "type": "object",
            "properties": {"x": {"type": "string"}},
        }
        model = json_schema_to_model("MyTool", schema)
        assert model.__name__ == "MyTool"

    def test_json_schema_round_trip(self) -> None:
        """Generated model can produce a valid JSON schema."""
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        }
        model = json_schema_to_model("SearchParams", schema)
        json_schema = model.model_json_schema()
        assert "query" in json_schema["properties"]
        assert "limit" in json_schema["properties"]
