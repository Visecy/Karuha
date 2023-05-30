import asyncio
from typing import Callable, ClassVar, Coroutine, List

from .. import bot


class BaseEvent(object):
    __slots__ = ["bot"]

    __handlers__: ClassVar[List[Callable[["BaseEvent"], Coroutine]]] = []

    def __init__(self, bot: "bot.Bot") -> None:
        self.bot = bot
    
    def process(self, task_creator: Callable[[Coroutine], asyncio.Task] = asyncio.create_task) -> None:
        for i in self.__handlers__:
            task_creator(i(self))
    
    def __init_subclass__(cls) -> None:
        if "__handlers__" not in cls.__dict__:
            cls.__handlers__ = cls.__handlers__.copy()
