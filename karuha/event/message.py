import asyncio
import json
from functools import partial
from typing import Dict, Union

from typing_extensions import Self

from ..bot import Bot
from ..text import BaseText, Drafty, Message
from ..utils.dispatcher import AbstractDispatcher
from ..utils.proxy_propery import ProxyProperty
from .bot import BotEvent, DataEvent


MessageProperty = partial(ProxyProperty, "message", mutable=True)


class MessageEvent(BotEvent):
    """a parsed DataMessage"""

    __slots__ = ["message"]

    def __init__(self, bot: Bot, /, topic: str, user_id: str, seq_id: int, head: Dict[str, str], content: bytes) -> None:
        super().__init__(bot)
        self.message = Message.new(bot, topic, user_id, seq_id, head, content)
    
    @classmethod
    def from_data_event(cls, event: DataEvent, /) -> Self:
        message = event.server_message
        return cls(
            event.bot,
            message.topic,
            message.from_user_id,
            message.seq_id,
            {k: json.loads(v) for k, v in message.head.items()},
            message.content
        )

    def dump(self) -> Message:
        return self.message
    
    topic: ProxyProperty[str] = MessageProperty()
    user_id: ProxyProperty[str] = MessageProperty()
    seq_id: ProxyProperty[int] = MessageProperty()
    content: ProxyProperty[bytes] = MessageProperty()
    raw_text: ProxyProperty[Union[str, Drafty]] = MessageProperty()
    text: ProxyProperty[Union[str, BaseText]] = MessageProperty()


class MessageDispatcher(AbstractDispatcher[Message]):
    __slots__ = []

    dispatchers = set()


_message_lock = None


def get_message_lock() -> asyncio.Lock:
    global _message_lock
    if _message_lock is None:
        _message_lock = asyncio.Lock()
    return _message_lock


def reset_message_lock() -> None:
    global _message_lock
    _message_lock = None
