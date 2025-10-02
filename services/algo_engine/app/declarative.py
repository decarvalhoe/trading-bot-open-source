"""Helpers to load declarative strategy definitions."""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from typing import Any, Dict, Mapping


try:  # pragma: no cover - import guarded for environments without PyYAML
    import yaml
except Exception:  # pragma: no cover - fallback handled at runtime
    yaml = None  # type: ignore[assignment]


class DeclarativeStrategyError(RuntimeError):
    """Raised when a declarative strategy cannot be parsed."""


SAFE_GLOBALS: Mapping[str, object] = {
    "__builtins__": {
        "True": True,
        "False": False,
        "None": None,
        "dict": dict,
        "list": list,
        "tuple": tuple,
        "set": set,
        "float": float,
        "int": int,
        "str": str,
        "max": max,
        "min": min,
        "sum": sum,
    }
}


@dataclass(slots=True)
class DeclarativeDefinition:
    name: str
    rules: list[dict[str, Any]]
    parameters: dict[str, Any]
    metadata: dict[str, Any]

    def to_parameters(self) -> Dict[str, Any]:
        params = dict(self.parameters)
        params.setdefault("definition", {
            "name": self.name,
            "rules": self.rules,
            "metadata": self.metadata,
        })
        return params


def _validate_definition(payload: Mapping[str, Any]) -> DeclarativeDefinition:
    if not isinstance(payload, Mapping):
        raise DeclarativeStrategyError("Declarative strategies must be defined as mappings")
    name = payload.get("name")
    rules = payload.get("rules", [])
    parameters = payload.get("parameters", {})
    metadata = payload.get("metadata", {})

    if not isinstance(name, str) or not name:
        raise DeclarativeStrategyError("Declarative strategy definitions require a non-empty 'name'")
    if not isinstance(rules, list):
        raise DeclarativeStrategyError("'rules' must be a list of rule definitions")
    if not isinstance(parameters, Mapping):
        raise DeclarativeStrategyError("'parameters' must be a mapping")
    if not isinstance(metadata, Mapping):
        raise DeclarativeStrategyError("'metadata' must be a mapping")

    for idx, rule in enumerate(rules):
        if not isinstance(rule, Mapping):
            raise DeclarativeStrategyError(f"Rule #{idx + 1} must be a mapping")
        if "when" not in rule or "signal" not in rule:
            raise DeclarativeStrategyError("Each rule must define 'when' and 'signal' sections")

    return DeclarativeDefinition(
        name=name,
        rules=list(rules),
        parameters=dict(parameters),
        metadata=dict(metadata),
    )


def load_declarative_definition(content: str, fmt: str) -> DeclarativeDefinition:
    """Load a declarative strategy definition from YAML or Python content."""

    fmt = fmt.lower()
    if fmt == "yaml":
        if yaml is not None:
            data = yaml.safe_load(content)  # type: ignore[no-untyped-call]
        else:
            try:
                data = json.loads(content)
            except json.JSONDecodeError as exc:
                raise DeclarativeStrategyError("PyYAML is required to load YAML strategies") from exc
    elif fmt == "python":
        namespace: Dict[str, Any] = {}
        try:
            compiled = ast.parse(content, mode="exec")
        except SyntaxError as exc:  # pragma: no cover - syntax errors bubble up
            raise DeclarativeStrategyError(f"Invalid Python strategy: {exc}") from exc
        exec(compile(compiled, "<strategy>", "exec"), dict(SAFE_GLOBALS), namespace)  # noqa: S102
        if "build_strategy" in namespace and callable(namespace["build_strategy"]):
            data = namespace["build_strategy"]()
        elif "STRATEGY" in namespace:
            data = namespace["STRATEGY"]
        else:
            raise DeclarativeStrategyError("Python strategies must define STRATEGY or build_strategy()")
    else:
        raise DeclarativeStrategyError("Unsupported declarative format; expected 'yaml' or 'python'")

    if data is None:
        raise DeclarativeStrategyError("Strategy definition is empty")

    return _validate_definition(data)


__all__ = [
    "DeclarativeDefinition",
    "DeclarativeStrategyError",
    "load_declarative_definition",
]
