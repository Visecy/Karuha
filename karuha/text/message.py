from typing import NamedTuple, Tuple, Union, Dict
from typing_extensions import Self

from ..bot import Bot
from ..logger import logger
from .drafty import Drafty
from .textchain import BaseText, PlainText
from .convert import drafty2text

try:
    import ujson as json
except ImportError:
    import json


class Message(NamedTuple):
    bot: Bot
    topic: str
    user_id: str
    seq_id: int
    head: Dict[str, str]
    content: bytes
    raw_text: Union[str, Drafty]
    text: Union[str, BaseText]

    @classmethod
    def new(cls, bot: Bot, topic: str, user_id: str, seq_id: int, head: Dict[str, str], content: bytes) -> Self:
        return cls(bot, topic, user_id, seq_id, head, content, *cls.parse_content(content))
    
    @staticmethod
    def parse_content(content: bytes) -> Tuple[Union[str, Drafty], Union[str, BaseText]]:
        try:
            raw_text = json.loads(content)
        except json.JSONDecodeError:
            raw_text = content.decode()
            logger.warning(f"cannot decode text {raw_text!r}")
        
        if not isinstance(raw_text, str):
            try:
                raw_text = Drafty.model_validate(raw_text)
            except Exception:
                logger.warning(f"unknown text format {raw_text!r}")
                raw_text = str(raw_text)
            else:
                try:
                    text = drafty2text(raw_text)
                except Exception:
                    logger.error(f"cannot decode drafty {raw_text!r}")
                    text = raw_text.txt
                return raw_text, text
        
        return raw_text, PlainText(raw_text)
