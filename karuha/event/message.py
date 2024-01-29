import json
from asyncio import Future
from typing import Any, Dict, NamedTuple, Optional, Union

from typing_extensions import Self

from ..bot import Bot
from ..text import Drafty, PlainText, BaseText, drafty2text
from .bot import BotEvent, DataEvent
from ..dispatcher import AbstractDispatcher, FutureDispatcher


class Message(NamedTuple):
    bot: Bot
    topic: str
    user_id: str
    seq_id: int
    head: Dict[str, str]
    content: bytes
    raw_text: Union[str, Drafty]
    text: Union[str, BaseText]


class MessageEvent(BotEvent):
    """a parsed DataMessage"""

    __slots__ = ["topic", "user_id", "seq_id", "head", "content", "raw_text", "text"]

    def __init__(self, bot: Bot, /, topic: str, user_id: str, seq_id: int, head: Dict[str, str], content: bytes) -> None:
        super().__init__(bot)
        self.topic = topic
        self.user_id = user_id
        self.seq_id = seq_id
        self.head = head
        self._set_text(content)
    
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
        return Message(
            self.bot,
            self.topic,
            self.user_id,
            self.seq_id,
            self.head,
            self.content,
            self.raw_text,
            self.text
        )
    
    def _set_text(self, content: bytes, /) -> None:
        self.content = content

        try:
            raw_text = json.loads(content)
        except json.JSONDecodeError:
            raw_text = content.decode()
            topic = self.topic
            seq_id = self.seq_id
            self.bot.logger.error(f"cannot decode text {raw_text!r} ({topic=},{seq_id=})")
        
        if not isinstance(raw_text, str):
            try:
                self.raw_text = Drafty.model_validate(raw_text)
            except Exception:
                self.bot.logger.error(f"unknown text format {raw_text!r}")
                raw_text = str(raw_text)
            else:
                try:
                    self.text = drafty2text(self.raw_text)
                except Exception:
                    self.bot.logger.error(f"cannot decode drafty {self.raw_text!r}")
                    self.text = self.raw_text.txt
                return
        
        self.raw_text = raw_text
        self.text = PlainText(raw_text)


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
