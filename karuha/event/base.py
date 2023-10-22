import asyncio
from typing import Any, Callable, ClassVar, Coroutine, List
from typing_extensions import Self

from ..logger import logger


class Event(object):
    __slots__ = []

    __handlers__: ClassVar[List[Callable[[Self], Coroutine]]] = []
    
    @classmethod
    def add_handler(cls, handler: Callable[[Self], Coroutine]) -> None:
        cls.__handlers__.append(handler)
    
    @classmethod
    def remove_handler(cls, handler: Callable[[Self], Coroutine]) -> None:
        cls.__handlers__.remove(handler)
    
    def call_handler(self, handler: Callable[[Self], Coroutine]) -> None:
        asyncio.create_task(handler(self))
    
    def trigger(self) -> None:
        logger.debug(f"trigger event {self.__class__.__name__}")
        for i in self.__handlers__:
            self.call_handler(i)
    
    def __init_subclass__(cls, **kwds: Any) -> None:
        if "__handlers__" not in cls.__dict__:
            cls.__handlers__ = cls.__handlers__.copy()
