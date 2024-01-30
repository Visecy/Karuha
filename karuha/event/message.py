import json
from asyncio import Future
from functools import partial
from typing import Any, Dict, Optional, Union

from typing_extensions import Self

from ..bot import Bot
from ..text import BaseText, Drafty, Message
from ..utils.dispatcher import AbstractDispatcher, FutureDispatcher
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


class MessageDispatcher(AbstractDispatcher[MessageEvent]):
    __slots__ = []

    dispatchers = set()


class ButtonReplyDispatcher(MessageDispatcher, FutureDispatcher[MessageEvent]):
    __slots__ = ["seq_id", "name", "value"]

    def __init__(self, /, future: Future, seq_id: int, name: Optional[str] = None, value: Optional[str] = None) -> None:
        super().__init__(future)
        self.seq_id = seq_id
        self.name = name
        self.value = value
    
    def match(self, message: MessageEvent) -> float:
        text = message.raw_text

        val: Dict[str, Any] = {"seq": self.seq_id}
        if self.name:
            val["resp"] = {self.name: self.value or 1}
        if isinstance(text, Drafty):
            for i in text.ent:
                if (
                    i.tp == "EX" and
                    i.data.get("mime") == "application/json" and
                    i.data.get("value") == val
                ):
                    return 2.5
        return 0
