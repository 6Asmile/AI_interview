from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Callable


@dataclass(frozen=True)
class OperationHandlerResult:
    """Normalized result returned by a registered operation handler."""

    result_type: str = ''
    result_id: str = ''
    result: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


OperationHandler = Callable[[Any], OperationHandlerResult | dict[str, Any] | None]

_handlers: dict[str, OperationHandler] = {}
_handler_lock = RLock()


def register_operation_handler(operation_type: str, handler: OperationHandler | None = None):
    """Register a stable operation type without storing executable paths in messages."""

    normalized = str(operation_type or '').strip()
    if not normalized or len(normalized) > 80:
        raise ValueError('invalid_operation_type')

    def decorator(callback: OperationHandler):
        with _handler_lock:
            existing = _handlers.get(normalized)
            if existing is not None and existing is not callback:
                raise ValueError(f'operation_handler_already_registered:{normalized}')
            _handlers[normalized] = callback
        return callback

    return decorator(handler) if handler is not None else decorator


def get_operation_handler(operation_type: str) -> OperationHandler:
    try:
        return _handlers[str(operation_type)]
    except KeyError as exc:
        raise LookupError(f'operation_handler_not_registered:{operation_type}') from exc


def unregister_operation_handler(operation_type: str, handler: OperationHandler | None = None) -> None:
    """Remove a handler, primarily for isolated tests and application shutdown."""

    with _handler_lock:
        current = _handlers.get(str(operation_type))
        if current is not None and (handler is None or current is handler):
            _handlers.pop(str(operation_type), None)
