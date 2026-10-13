from collections.abc import Callable, Iterator
from copy import deepcopy
from typing import Any

COMPONENT_KINDS = {
    "schemas": "schema",
    "parameters": "parameter",
    "headers": "parameter",
    "requestBodies": "request_body",
    "responses": "response",
    "pathItems": "path_item",
    "examples": "example",
    "links": "link",
    "callbacks": "callback",
    "securitySchemes": "security_scheme",
}
_CHILDREN = {
    "document": {
        "paths": "map:path_item",
        "webhooks": "map:path_item",
        "components": "components",
    },
    "components": {name: f"map:{kind}" for name, kind in COMPONENT_KINDS.items()},
    "path_item": {
        **dict.fromkeys(
            ("get", "put", "post", "delete", "options", "head", "patch", "trace"),
            "operation",
        ),
        "parameters": "list:parameter",
    },
    "operation": {
        "parameters": "list:parameter",
        "requestBody": "request_body",
        "responses": "map:response",
        "callbacks": "map:callback",
    },
    "request_body": {"content": "map:media"},
    "parameter": {"schema": "schema", "content": "map:media"},
    "response": {
        "content": "map:media",
        "headers": "map:parameter",
        "links": "map:link",
    },
    "media": {
        "schema": "schema",
        "examples": "map:example",
        "encoding": "map:encoding",
    },
    "encoding": {"headers": "map:parameter"},
    "schema": {
        **dict.fromkeys(
            (
                "properties",
                "patternProperties",
                "$defs",
                "definitions",
                "dependentSchemas",
            ),
            "map:schema",
        ),
        **dict.fromkeys(("allOf", "oneOf", "anyOf", "prefixItems"), "list:schema"),
        **dict.fromkeys(
            (
                "items",
                "additionalProperties",
                "additionalItems",
                "not",
                "contains",
                "propertyNames",
                "if",
                "then",
                "else",
                "unevaluatedProperties",
                "unevaluatedItems",
            ),
            "schema",
        ),
        "discriminator": "discriminator",
    },
}
REFERENCE_KINDS = {
    "schema",
    "parameter",
    "request_body",
    "response",
    "path_item",
    "example",
    "link",
    "callback",
    "security_scheme",
}


def openapi_nodes(
    value: Any, kind: str = "document"
) -> Iterator[tuple[dict[str, Any], str]]:
    if kind.startswith("map:"):
        if isinstance(value, dict):
            for child in value.values():
                yield from openapi_nodes(child, kind[4:])
        return
    if kind.startswith("list:") or (
        kind == "schema" and isinstance(value, (list, tuple))
    ):
        if isinstance(value, (list, tuple)):
            for child in value:
                yield from openapi_nodes(child, kind.removeprefix("list:"))
        return
    if not isinstance(value, dict):
        return
    yield value, kind
    if kind == "callback":
        for name, child in value.items():
            if name != "$ref" and not name.startswith("x-"):
                yield from openapi_nodes(child, "path_item")
    for name, child_kind in _CHILDREN.get(kind, {}).items():
        if name in value:
            yield from openapi_nodes(value[name], child_kind)


def reference_values(
    value: Any, kind: str = "document", *, mappings: bool = False
) -> Iterator[str]:
    for node, node_kind in openapi_nodes(value, kind):
        if node_kind in REFERENCE_KINDS and isinstance(node.get("$ref"), str):
            yield node["$ref"]
        if mappings and node_kind == "discriminator":
            for target in node.get("mapping", {}).values():
                if isinstance(target, str):
                    yield (
                        target
                        if target.startswith("#/")
                        else f"#/components/schemas/{target}"
                    )


def rewrite_references(
    value: Any, transform: Callable[[str], str], kind: str = "document"
) -> Any:
    result = deepcopy(value)
    for node, node_kind in openapi_nodes(result, kind):
        if node_kind in REFERENCE_KINDS and isinstance(node.get("$ref"), str):
            node["$ref"] = transform(node["$ref"])
        if node_kind == "discriminator":
            node["mapping"] = {
                name: transform(target)
                for name, target in node.get("mapping", {}).items()
            }
    return result
