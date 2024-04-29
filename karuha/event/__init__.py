from asyncio import iscoroutinefunction
from typing import Any, Callable, Type, TypeVar

from .base import Event


T_Event = TypeVar("T_Event", bound=Event)


def on(event: Type[T_Event]) -> Callable[[Callable[[T_Event], Any]], Callable[[T_Event], Any]]:
    def wrapper(func: Callable[[T_Event], Any]) -> Callable[[T_Event], Any]:
        if not iscoroutinefunction(func):
            async def wrapper(event: T_Event) -> Any:
                return func(event)
            event.add_handler(wrapper)
        else:
            event.add_handler(func)
        return func
    return wrapper


on_event = on


__all__ = [
    "on",
    "Event",
]