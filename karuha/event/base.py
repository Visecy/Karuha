from abc import ABC, abstractmethod

from ..bot import Bot


class BaseEvent(ABC):
    __slots__ = ["bot"]

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @abstractmethod
    async def __call__(self) -> None:
        raise NotImplementedError
