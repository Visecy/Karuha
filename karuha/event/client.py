
from typing import Union

from .. import bot
from ..text import DraftyMessage, BaseText
from .base import BaseEvent


class ClientEvent(BaseEvent):
    __slots__ = []

    async def default_handler(self) -> None:
        pass
    
    def trigger(self) -> None:
        self.bot._create_task(self.default_handler())
        return super().trigger()


class PublishEvent(ClientEvent):
    __slots__ = ["text", "topic"]

    def __init__(self, bot: "bot.Bot", topic: str, text: Union[str, DraftyMessage, BaseText]) -> None:
        super().__init__(bot)
        self.text = text
        self.topic = topic

    async def default_handler(self) -> None:
        text = self.text
        if isinstance(text, str):
            await self.bot.publish(self.topic, text)
        else:
            if isinstance(text, BaseText):
                text = text.to_drafty()
            await self.bot.publish(
                self.topic,
                text.dict(),
                head={"auto": True, "mime": "text/x-drafty"}
            )


class SubscribeEvent(ClientEvent):
    __slots__ = ["topic"]

    def __init__(self, bot: "bot.Bot", topic: str) -> None:
        super().__init__(bot)
        self.topic = topic
    
    async def default_handler(self) -> None:
        await self.bot.subscribe(self.topic)


class LeaveEvent(ClientEvent):
    __slots__ = ["topic"]

    def __init__(self, bot: "bot.Bot", topic: str) -> None:
        super().__init__(bot)
        self.topic = topic
    
    async def default_handler(self) -> None:
        await self.bot.leave(self.topic)
