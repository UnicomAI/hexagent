"""JSON Schema to Pydantic model conversion for MCP tool inputs.

Converts MCP tool ``inputSchema`` (a JSON Schema ``dict``) into a dynamic
Pydantic ``BaseModel`` subclass that can be assigned to
``BaseAgentTool.args_schema``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, create_model


def json_schema_to_model(name: str, schema: dict[str, Any]) -> type[BaseModel]:
    """Convert a JSON Schema object to a Pydantic BaseModel class.

    Args:
        name: PascalCase class name for the generated model.
        schema: JSON Schema dict (``inputSchema`` from an MCP Tool).

    Returns:
        A dynamically generated BaseModel subclass.
    """
    properties: dict[str, Any] = schema.get("properties", {})
    required: set[str] = set(schema.get("required", []))

    field_definitions: dict[str, Any] = {}
    for field_name, prop_schema in properties.items():
        python_type = _resolve_type(prop_schema, f"{name}_{field_name}")
        description = prop_schema.get("description", "")

        if field_name in required:
            field_definitions[field_name] = (
                python_type,
                Field(..., description=description) if description else ...,
            )
        elif "default" in prop_schema and prop_schema["default"] is not None:
            default = prop_schema["default"]
            field_definitions[field_name] = (
                python_type,
                Field(default=default, description=description) if description else default,
            )
        else:
            field_definitions[field_name] = (
                python_type | None,
                Field(default=None, description=description) if description else None,
            )

    return create_model(name, **field_definitions)


def _resolve_type(prop_schema: dict[str, Any], parent_name: str) -> Any:  # noqa: ANN401, PLR0911
    """Recursively resolve a JSON Schema property to a Python type annotation.

    Args:
        prop_schema: JSON Schema for a single property.
        parent_name: Name context for nested model generation.

    Returns:
        A Python type suitable for Pydantic field annotation.
    """
    # Handle anyOf / oneOf — collapse to Any
    if "anyOf" in prop_schema or "oneOf" in prop_schema:
        return Any

    type_value = prop_schema.get("type")

    # Array-style nullable: {"type": ["string", "null"]}
    if isinstance(type_value, list):
        non_null = [t for t in type_value if t != "null"]
        if len(non_null) == 1:
            resolved = _resolve_type({"type": non_null[0]}, parent_name)
            return resolved if "null" not in type_value else resolved | None
        return Any

    type_map: dict[str, type[Any]] = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
    }

    if type_value in type_map:
        return type_map[type_value]

    if type_value == "null":
        return type(None)

    if type_value == "array":
        items_schema = prop_schema.get("items")
        if items_schema and isinstance(items_schema, dict):
            item_type = _resolve_type(items_schema, f"{parent_name}_Item")
            return list[item_type]  # type: ignore[valid-type]
        return list[Any]

    if type_value == "object":
        nested_props = prop_schema.get("properties")
        if nested_props:
            return json_schema_to_model(_to_pascal_case(parent_name), prop_schema)
        return dict[str, Any]

    # Unknown or missing type
    return Any


def _to_pascal_case(s: str) -> str:
    """Convert a snake_case or underscore-separated string to PascalCase."""
    return "".join(part.capitalize() for part in s.split("_") if part)
