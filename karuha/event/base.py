import asyncio
from typing import Callable, ClassVar, Coroutine, List
from typing_extensions import Self

from .. import bot


class BaseEvent(object):
    __slots__ = ["bot"]

    __handlers__: ClassVar[List[Callable[[Self], Coroutine]]] = []

    def __init__(self, bot: "bot.Bot") -> None:
        self.bot = bot
    
    def trigger(self, task_creator: Callable[[Coroutine], asyncio.Task] = asyncio.create_task) -> None:
        for i in self.__handlers__:
            task_creator(i(self))
    
    @classmethod
    def add_handler(cls, handler: Callable[[Self], Coroutine]) -> None:
        cls.__handlers__.append(handler)
    
    @classmethod
    def remove_handler(cls, handler: Callable[[Self], Coroutine]) -> None:
        cls.__handlers__.remove(handler)
    
    def __init_subclass__(cls) -> None:
        if "__handlers__" not in cls.__dict__:
            cls.__handlers__ = cls.__handlers__.copy()
