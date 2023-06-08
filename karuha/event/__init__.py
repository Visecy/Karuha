from typing import Any, Callable, Type, TypeVar

from .base import BaseEvent
from .server import DataEvent, CtrlEvent, MetaEvent, PresEvent, InfoEvent


T_Event = TypeVar("T_Event", bound=BaseEvent)


def on(event: Type[T_Event]) -> Callable[[Callable[[T_Event], Any]], Callable[[T_Event], Any]]:
    def wrapper(func: Callable[[T_Event], Any]) -> Callable[[T_Event], Any]:
        event.add_handler(func)
        return func
    return wrapper


__all__ = [
    "BaseEvent",
    "DataEvent",
    "CtrlEvent",
    "MetaEvent",
    "PresEvent",
    "InfoEvent"
]