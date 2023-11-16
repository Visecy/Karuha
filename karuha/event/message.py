import json
from typing import Dict
from typing_extensions import Self

from ..bot import Bot
from ..text import Drafty, PlainText, drafty2text
from .bot import BotEvent, DataEvent


class MessageEvent(BotEvent):
    __slots__ = ["topic", "uid", "seq_id", "head", "raw_content", "raw_text", "text"]

    def __init__(self, bot: Bot, /, topic: str, uid: str, seq_id: int, head: Dict[str, str], content: bytes) -> None:
        super().__init__(bot)
        self.topic = topic
        self.uid = uid
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
    
    def _set_text(self, content: bytes, /) -> None:
        self.raw_content = content

        try:
            raw_text = json.loads(content)
        except json.JSONDecodeError:
            raw_text = content.decode()
            topic = self.topic
            seq_id = self.seq_id
            self.bot.logger.error(f"cannot decode text {raw_text} ({topic=},{seq_id=})")
        
        if not isinstance(raw_text, str):
            try:
                self.raw_text = Drafty.model_validate(raw_text)
            except Exception:
                self.bot.logger.error(f"unknown text format {raw_text}")
                raw_text = str(raw_text)
            else:
                try:
                    self.text = drafty2text(self.raw_text)
                except Exception:
                    self.bot.logger.error(f"cannot decode drafty {self.raw_text}")
                    self.text = self.raw_text.txt
                return
        
        self.raw_text = raw_text
        self.text = PlainText(raw_text)
