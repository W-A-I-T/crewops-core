from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


DepartmentHandler = Callable[[str], Any]
DeliveryHandler = Callable[[dict[str, Any]], Any]


@dataclass
class RuntimeRegistry:
    departments: dict[str, DepartmentHandler] = field(default_factory=dict)
    seed_entities: dict[str, tuple[str, str, list[str]]] = field(default_factory=dict)
    delivery_adapters: dict[str, DeliveryHandler] = field(default_factory=dict)

    def register_department(self, name: str, handler: DepartmentHandler) -> None:
        self.departments[name.strip().lower()] = handler

    def register_seed_entities(self, entities: dict[str, tuple[str, str, list[str]]]) -> None:
        self.seed_entities.update(entities)

    def register_delivery_adapter(self, name: str, handler: DeliveryHandler) -> None:
        self.delivery_adapters[name.strip().lower()] = handler

    def list_departments(self) -> list[str]:
        return sorted(self.departments)

    def dispatch(self, dept: str, request: str) -> Any:
        key = dept.strip().lower()
        if key not in self.departments:
            raise KeyError(f"Unknown department: {dept}")
        handler = self.departments[key]
        result = handler(request)
        if inspect.isawaitable(result):
            close = getattr(result, "close", None)
            if callable(close):
                close()
            raise TypeError("Async department handlers are not supported in the sync runtime")
        return result


_runtime = RuntimeRegistry()


def get_runtime() -> RuntimeRegistry:
    return _runtime


def register_department(name: str, handler: DepartmentHandler) -> None:
    _runtime.register_department(name, handler)


def register_seed_entities(entities: dict[str, tuple[str, str, list[str]]]) -> None:
    _runtime.register_seed_entities(entities)


def register_delivery_adapter(name: str, handler: DeliveryHandler) -> None:
    _runtime.register_delivery_adapter(name, handler)
