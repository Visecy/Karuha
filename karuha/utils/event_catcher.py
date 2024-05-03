import asyncio
from typing import Generic, Optional, Type, TypeVar

from ..event import Event
from .context import _ContextHelper


T_Event = TypeVar("T_Event", bound=Event)


class EventCatcher(Generic[T_Event], _ContextHelper):
    __slots__ = ["event_type", "future", "events"]

    def __init__(self, event_type: Type[T_Event]) -> None:
        self.event_type = event_type
        self.events = []
        self.future = None
    
    def catch_event_nowait(self) -> T_Event:
        return self.events.pop()
    
    async def catch_event(self, timeout: Optional[float] = None) -> T_Event:
        if self.events:
            return self.catch_event_nowait()
        assert self.future is None, "catcher is already waited"
        loop = asyncio.get_running_loop()
        self.future = loop.create_future()
        try:
            return await asyncio.wait_for(self.future, timeout)
        finally:
            self.future = None
    
    @property
    def caught(self) -> bool:
        return bool(self.events)

    def activate(self) -> None:
        self.event_type.add_handler(self)
    
    def deactivate(self) -> None:
        self.event_type.remove_handler(self)

    async def __call__(self, event: T_Event) -> None:
        if self.future:
            self.future.set_result(event)
        else:
            self.events.append(event)
