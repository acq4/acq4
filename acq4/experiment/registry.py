"""Registry mapping serialized type names to Action classes, so protocols can be
(de)serialized by type name."""
from __future__ import annotations

from .action import Action

_REGISTRY: dict[str, type] = {}


def register_action(cls: type | None = None, *, name: str | None = None):
    """Class decorator registering an Action subclass under `name`
    (default: the class name)."""

    def _reg(c):
        key = name or c.__name__
        existing = _REGISTRY.get(key)
        if existing is not None and existing is not c:
            raise ValueError(f"Action type {key!r} already registered")
        _REGISTRY[key] = c
        c._typeName = key
        return c

    return _reg(cls) if cls is not None else _reg


def get_action_class(name: str) -> type:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown action type {name!r}")
    return _REGISTRY[name]


def action_type_name(action: Action) -> str:
    return getattr(type(action), "_typeName", type(action).__name__)
