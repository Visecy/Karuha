from collections import deque
from inspect import Parameter
import re
from typing import Any, Dict, Optional, Tuple, TypeVar, Union

from pydantic import BeforeValidator
from pydantic_core import core_schema, from_json
from typing_extensions import Annotated, Self, get_args

from karuha.exception import KaruhaHandlerInvokerError

from ..bot import Bot
from ..logger import logger
from ..utils.invoker import HandlerInvokerModel
from .convert import drafty2text
from .drafty import Drafty
from .textchain import BaseText, PlainText


class Message(HandlerInvokerModel, frozen=True, arbitrary_types_allowed=True):  # type: ignore
    bot: Bot
    topic: str
    user_id: str
    seq_id: int
    head: Dict[str, Any]
    content: bytes
    raw_text: Union[str, Drafty]
    text: Union[str, BaseText]

    @classmethod
    def new(cls, bot: Bot, topic: str, user_id: str, seq_id: int, head: Dict[str, Any], content: bytes) -> Self:
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
            raw_text = from_json(content)
        except ValueError:
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
    
    def get_dependency(self, param: Parameter) -> Any:
        if param.name == "text":
            try:
                return self.validate_dependency(param, self.text)
            except KaruhaHandlerInvokerError:
                pass
            return self.validate_dependency(param, self.plain_text)
        return super().get_dependency(param)
    
    def resolve_missing_dependencies(self, missing: Dict[Parameter, KaruhaHandlerInvokerError]) -> Dict[str, Any]:
        dependencies = {}
        still_missing = {}
        for param, error in missing.items():
            if param.annotation is not param.empty and is_message_extend_type(param.annotation):
                val = self.validate_dependency(param, self)
                dependencies[param.name] = val
            else:
                still_missing[param] = error
        if still_missing:
            dependencies.update(super().resolve_missing_dependencies(still_missing))
        return dependencies
        
    @property
    def plain_text(self) -> str:
        return str(self.text)

    @property
    def message(self) -> Self:
        return self
    
    @property
    def session(self) -> "MessageSession":
        return MessageSession(self.bot, self)


from ..session import BaseSession


class MessageSession(BaseSession):
    __slots__ = ["_messages"]

    def __init__(self, /, bot: Bot, message: Message) -> None:
        super().__init__(bot, message.topic)
        self._messages = deque((message,))
    
    async def wait_reply(
            self,
            topic: Optional[str] = None,
            user_id: Optional[str] = None,
            pattern: Optional[re.Pattern] = None,
            priority: float = 1.2
    ) -> Message:
        message = await super().wait_reply(topic, user_id, pattern, priority)
        self._add_message(message)
        return message
    
    def _add_message(self, message: Message) -> None:
        assert message.bot is self.bot
        if message.topic != self.topic:
            return
        self._messages.append(message)

    @property
    def messages(self) -> Tuple[Message, ...]:
        return tuple(self._messages)
    
    @property
    def last_message(self) -> Message:
        return self._messages[-1]


MESSAGE_EXTEND_TYPE_FLAG = object()


def is_message_extend_type(tp: Any) -> bool:
    return MESSAGE_EXTEND_TYPE_FLAG in get_args(tp)


def _head_getter(msg: Message, info: core_schema.ValidationInfo) -> Any:
    assert info.context is not None
    return msg.head.get(info.context["name"])


T = TypeVar("T")
Head = Annotated[T, BeforeValidator(_head_getter), MESSAGE_EXTEND_TYPE_FLAG]
