"""Loading and validation shared by the editable content files.

Each helper takes a `what` label so a malformed file names itself in the error
an operator sees, rather than collapsing every failure into one message.
"""

from typing import Any

import yaml


def parse_yaml_mapping(text: str, what: str) -> dict[str, Any]:
    parsed: Any = yaml.safe_load(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"{what} must be a YAML mapping")
    return parsed


def require_text(mapping: dict[str, Any], key: str, what: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{what} must define a non-empty {key}")
    return value


def require_text_list(mapping: dict[str, Any], key: str, what: str) -> tuple[str, ...]:
    value = mapping.get(key)
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise ValueError(f"{what} must define {key} as a non-empty list of strings")
    return tuple(value)
