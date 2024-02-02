import asyncio
from types import TracebackType
from typing import Generic, Optional, Type
from typing_extensions import Self

from ..event import T_Event


class EventCatcher(Generic[T_Event]):
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
        assert self.future is None, "catcher is already waiting"
        loop = asyncio.get_running_loop()
        self.future = loop.create_future()
        try:
            return await asyncio.wait_for(self.future, timeout)
        finally:
            self.future = None
    
    @property
    def caught(self) -> bool:
        return bool(self.events)

    async def __call__(self, event: T_Event) -> None:
        if self.future:
            self.future.set_result(event)
        else:
            self.events.append(event)
    
    def __enter__(self) -> Self:
        self.event_type.add_handler(self)
        return self
    
    def __exit__(self, exec_type: Type[BaseException], exec_ins: BaseException, traceback: TracebackType) -> None:
        self.event_type.remove_handler(self)
