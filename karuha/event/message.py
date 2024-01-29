import json
from asyncio import Future
from typing import Any, Dict, Optional, Type

from typing_extensions import Self

from ..bot import Bot
from ..text import Drafty, Message
from .bot import BotEvent, DataEvent
from ..dispatcher import AbstractDispatcher, FutureDispatcher


class MessageProperty:
    __slots__ = ["name"]

    def __set_name__(self, owner: Type["MessageEvent"], name: str, /) -> None:
        self.name = name
    
    def __get__(self, instance: "MessageEvent", owner: Type["MessageEvent"], /) -> Any:
        return getattr(instance.message, self.name)


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
    
    topic = MessageProperty()
    user_id = MessageProperty()
    seq_id = MessageProperty()
    content = MessageProperty()
    raw_text = MessageProperty()
    text = MessageProperty()


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
