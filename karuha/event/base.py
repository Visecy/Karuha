import asyncio
import sys
from logging import Logger
from typing import Any, Awaitable, Callable, ClassVar, List
from typing_extensions import Self, ParamSpec

from ..logger import logger
from ..utils.locks import Lock
from ..utils.invoker import HandlerInvoker


P = ParamSpec("P")


async def handler_runner(event: "Event", logger: Logger, func: Callable) -> Any:
    try:
        ret = super(Event, event).call_handler(func)
        if asyncio.iscoroutine(ret):
            ret = await ret
        return ret
    except Exception as e:
        logger.exception(f"a handler of the event {event} failed", exc_info=sys.exc_info())
        return e


class Event(HandlerInvoker):
    """base class for all events"""

    __slots__ = []

    __handlers__: ClassVar[List[Callable[..., Any]]] = []
    __event_lock__: ClassVar[Lock]
    
    @classmethod
    def add_handler(cls, handler: Callable[..., Any]) -> None:
        cls.__handlers__.append(handler)
    
    @classmethod
    def remove_handler(cls, handler: Callable[..., Any]) -> None:
        cls.__handlers__.remove(handler)
    
    @classmethod  # type: ignore
    def new(cls: Callable[P, Self], *args: P.args, **kwds: P.kwargs) -> Self:  # type: ignore
        event = cls(*args, **kwds)
        event.trigger(return_exceptions=True)
        return event
    
    @classmethod  # type: ignore
    async def new_and_wait(cls: Callable[P, Self], *args: P.args, **kwds: P.kwargs) -> Self:  # type: ignore
        event = cls(*args, **kwds)
        await event.trigger()
        return event
    
    def call_handler(self, handler: Callable[..., Any]) -> Awaitable:
        return asyncio.create_task(handler_runner(self, logger, handler))
    
    def trigger(self, *, return_exceptions: bool = False) -> "asyncio.Future[list]":
        logger.debug(f"trigger event {self.__class__.__name__}")
        return asyncio.gather(
            *(self.call_handler(i) for i in self.__handlers__),
            return_exceptions=return_exceptions
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
        super().__init_subclass__(**kwds)
        if "__handlers__" not in cls.__dict__:
            cls.__handlers__ = cls.__handlers__.copy()
        if "__default_handler__" in cls.__dict__:
            cls.__handlers__.append(cls.__default_handler__)  # type: ignore


Event.register_dependency("lock", lambda self, _: self.get_lock())
Event.register_dependency("self", lambda self, _: self)
Event.register_dependency("event", lambda self, _: self)
