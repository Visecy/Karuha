from typing import Callable, Type, TypeVar

from .base import Event


_T_Callable = TypeVar("_T_Callable", bound=Callable)


def on(event: Type[Event]) -> Callable[[_T_Callable], _T_Callable]:
    def wrapper(func: _T_Callable) -> _T_Callable:
        event.add_handler(func)
        return func
    return wrapper


on_event = on


__all__ = [
    "on",
    "Event",
]