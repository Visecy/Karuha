import asyncio
from typing import Any, Awaitable, Callable, ClassVar, Coroutine, List
from typing_extensions import Self, ParamSpec

from ..logger import logger
from ..utils.locks import Lock


P = ParamSpec("P")


class Event(object):
    """base class for all events"""

    __slots__ = []

    __handlers__: ClassVar[List[Callable[[Self], Coroutine]]] = []
    __event_lock__: ClassVar[Lock] = Lock()
    
    @classmethod
    def add_handler(cls, handler: Callable[[Self], Coroutine]) -> None:
        cls.__handlers__.append(handler)
    
    @classmethod
    def remove_handler(cls, handler: Callable[[Self], Coroutine]) -> None:
        cls.__handlers__.remove(handler)
    
    @classmethod  # type: ignore
    def new(cls: Callable[P, Self], *args: P.args, **kwds: P.kwargs) -> Self:  # type: ignore
        event = cls(*args, **kwds)
        event.trigger()
        return event
    
    def call_handler(self, handler: Callable[[Self], Coroutine]) -> Awaitable:
        return asyncio.create_task(handler(self))
    
    def trigger(self) -> "asyncio.Future[list]":
        logger.debug(f"trigger event {self.__class__.__name__}")
        return asyncio.gather(
            *(self.call_handler(i) for i in self.__handlers__)
        )
    
    @classmethod
    def get_lock(cls) -> Lock:
        loop = asyncio.get_running_loop()
        lock = cls.__dict__.get("__event_lock__")
        if lock is None or (lock._loop is not None and lock._loop is not loop):
            lock = Lock()
            cls.__event_lock__ = lock
        return lock
    
    def __init_subclass__(cls, **kwds: Any) -> None:
        if "__handlers__" not in cls.__dict__:
            cls.__handlers__ = cls.__handlers__.copy()
