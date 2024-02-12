from typing import Any, Callable, Type, TypeVar

from .base import Event


T_Event = TypeVar("T_Event", bound=Event)


def on(event: Type[T_Event]) -> Callable[[Callable[[T_Event], Any]], Callable[[T_Event], Any]]:
    def wrapper(func: Callable[[T_Event], Any]) -> Callable[[T_Event], Any]:
        event.add_handler(func)
        return func
    return wrapper


on_event = on


__all__ = [
    "on",
    "Event",
]