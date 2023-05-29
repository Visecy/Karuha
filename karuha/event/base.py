from abc import ABC, abstractmethod

from .. import bot


class BaseEvent(ABC):
    __slots__ = ["bot"]

    def __init__(self, bot: "bot.Bot") -> None:
        self.bot = bot

    @abstractmethod
    async def __call__(self) -> None:
        raise NotImplementedError
