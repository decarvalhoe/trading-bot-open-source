"""Strategy plugin base classes and registry helpers."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, Iterable, List, MutableMapping, Type


@dataclass
class StrategyConfig:
    """Container for strategy configuration metadata."""

    name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = False
    tags: Iterable[str] | None = None


class StrategyBase(abc.ABC):
    """Base class that all strategies must inherit from."""

    #: Unique identifier for the strategy type.
    key: ClassVar[str]

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config

    @abc.abstractmethod
    def generate_signals(self, market_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Produce trading signals for the provided market snapshot."""

    def __repr__(self) -> str:  # pragma: no cover - trivial representation helper
        return f"{self.__class__.__name__}(name={self.config.name!r})"


class StrategyRegistry:
    """Global registry used to discover and instantiate strategies."""

    def __init__(self) -> None:
        self._registry: MutableMapping[str, Type[StrategyBase]] = {}

    def register(self, strategy_cls: Type[StrategyBase]) -> Type[StrategyBase]:
        key = getattr(strategy_cls, "key", None)
        if not key:
            raise ValueError("Strategy classes must define a 'key' class attribute")
        if key in self._registry:
            raise KeyError(f"Strategy '{key}' already registered")
        self._registry[key] = strategy_cls
        return strategy_cls

    def create(self, key: str, config: StrategyConfig) -> StrategyBase:
        try:
            strategy_cls = self._registry[key]
        except KeyError as exc:
            raise KeyError(f"Unknown strategy '{key}'") from exc
        return strategy_cls(config)

    def available_strategies(self) -> List[str]:
        return sorted(self._registry.keys())


registry = StrategyRegistry()


def register_strategy(cls: Type[StrategyBase]) -> Type[StrategyBase]:
    """Decorator that registers the decorated strategy class."""

    registry.register(cls)
    return cls


__all__ = [
    "StrategyBase",
    "StrategyConfig",
    "StrategyRegistry",
    "register_strategy",
    "registry",
]
