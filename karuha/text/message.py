from typing import Any, Tuple, Union, Dict
from typing_extensions import Self
from pydantic import BaseModel

from ..bot import Bot
from ..logger import logger
from .drafty import Drafty
from .textchain import BaseText, PlainText
from .convert import drafty2text

try:
    import ujson as json
except ImportError:  # pragma: no cover
    import json


class Message(BaseModel, frozen=True, arbitrary_types_allowed=True):
    bot: Bot
    topic: str
    user_id: str
    seq_id: int
    head: Dict[str, Any]
    content: bytes
    raw_text: Union[str, Drafty]
    text: Union[str, BaseText]

    @classmethod
    def new(cls, bot: Bot, topic: str, user_id: str, seq_id: int, head: Dict[str, str], content: bytes) -> Self:
        raw_text, text = cls.parse_content(content)
        return cls(
            bot=bot,
            topic=topic,
            user_id=user_id,
            seq_id=seq_id,
            head=head,
            content=content,
            raw_text=raw_text,
            text=text
        )
    
    @staticmethod
    def parse_content(content: bytes) -> Tuple[Union[str, Drafty], Union[str, BaseText]]:
        try:
            raw_text = json.loads(content)
        except json.JSONDecodeError:
            raw_text = content.decode(errors="ignore")
            logger.warning(f"cannot decode text {raw_text!r}")
        
        if isinstance(raw_text, str):
            return raw_text, PlainText(raw_text)
        
        try:
            raw_text = Drafty.model_validate(raw_text)
        except Exception:
            logger.warning(f"unknown text format {raw_text!r}")
            raw_text = text = str(raw_text)
        else:
            try:
                text = drafty2text(raw_text)
            except Exception:
                logger.error(f"cannot decode drafty {raw_text!r}")
                text = raw_text.txt
        return raw_text, text
        
    @property
    def plain_text(self) -> str:
        return str(self.text)
