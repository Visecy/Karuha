import asyncio
import os
from collections import deque
from typing import Any, Dict, Optional, Tuple, Union

from aiofiles import open as aio_open
from typing_extensions import Self

from ..bot import Bot
from ..utils.dispatcher import FutureDispatcher
from ..event.message import MessageDispatcher, MessageEvent, Message
from ..text import BaseText, Drafty, File


class BaseSession(object):
    __slots__ = ["bot", "topic"]

    def __init__(self, /, bot: Bot, topic: str) -> None:
        self.bot = bot
        self.topic = topic
    
    async def send(self, text: Union[str, dict, Drafty, BaseText], /, *, head: Optional[Dict[str, Any]] = None) -> None:
        if isinstance(text, BaseText):
            text = text.to_drafty()
        if isinstance(text, Drafty):
            text = text.model_dump()
            head = head or {}
            head["mime"] = "text/x-drafty"
        await self.bot.publish(self.topic, text, head=head)
    
    send_text = send

    async def send_file(self, path: Union[str, bytes, os.PathLike], /, *, name: Optional[str] = None) -> None:
        async with aio_open(path, "rb") as f:
            data = await f.read()
        file = File(
            raw_value=data,  # type: ignore
            name=name
        )
        await self.send(file)
    
    async def subscribe(self, /, get_since: Optional[int] = None, limit: int = 24) -> None:
        await self.bot.subscribe(self.topic, get_since=get_since, limit=limit)
    
    async def leave(self) -> None:
        await self.bot.leave(self.topic)


class MessageSession(BaseSession):
    __slots__ = ["_messages"]

    def __init__(self, /, bot: Bot, message: Message) -> None:
        super().__init__(bot, message.topic)
        self._messages = deque((message,))
    
    @classmethod
    def from_message_event(cls, event: MessageEvent) -> Self:
        return cls(event.bot, event.dump())

    @property
    def messages(self) -> Tuple[Message, ...]:
        return tuple(self._messages)
    
    @property
    def last_message(self) -> Message:
        return self._messages[-1]


class BaseSessionDispatcher(MessageDispatcher, FutureDispatcher[MessageEvent]):
    __slots__ = ["session"]

    def __init__(self, session: BaseSession, /, future: asyncio.Future, *, once: bool = False) -> None:
        self.session = session
        super().__init__(future=future, once=once)
    
    @classmethod
    def new(cls, session: BaseSession, /, loop: Optional[asyncio.AbstractEventLoop] = None, *, once: bool = False) -> Self:
        future = asyncio.Future(loop=loop)
        return cls(session, future=future, once=once)
