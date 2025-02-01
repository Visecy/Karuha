from inspect import Parameter
import sys
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple, Type, TypeVar, Union, cast

from pydantic import computed_field
from pydantic_core import from_json
from typing_extensions import Annotated, Self

from ..bot import Bot
from ..exception import KaruhaHandlerInvokerError
from ..logger import logger
from ..utils.invoker import HandlerInvokerModel, HandlerInvokerDependency
from .convert import drafty2text
from .drafty import Drafty
from .textchain import BaseText, PlainText, Quote, TextChain


class Message(HandlerInvokerModel, frozen=True, arbitrary_types_allowed=True):  # type: ignore
    bot: Bot
    topic: str
    user_id: str
    seq_id: int
    head: Dict[str, Any]
    content: bytes
    raw_text: Union[str, Drafty]
    text: Union[str, BaseText]
    quote: Optional[Quote]

    @classmethod
    def new(cls, bot: Bot, topic: str, user_id: str, seq_id: int, head: Dict[str, Any], content: bytes) -> Self:
        raw_text, text = cls.parse_content(content)
        if isinstance(text, TextChain) and isinstance(text[0], Quote):
            quote = cast(Quote, text[0])
            text = text[1:].take()
        else:
            quote = None
        return cls(
            bot=bot,
            topic=topic,
            user_id=user_id,
            seq_id=seq_id,
            head=head,
            content=content,
            raw_text=raw_text,
            text=text,
            quote=quote,
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
            logger.warning(f"unknown text format {raw_text!r}", exc_info=sys.exc_info())
            raw_text = text = str(raw_text)
        else:
            try:
                text = drafty2text(raw_text)
            except Exception:  # pragma: no cover
                logger.error(f"cannot decode drafty {raw_text!r}")
                text = raw_text.txt
        return raw_text, text

    def get_dependency(self, param: Parameter, /, **kwds: Any) -> Any:
        if param.name == "text":
            try:
                return self.validate_dependency(param, self.text, **kwds)
            except KaruhaHandlerInvokerError:
                if not isinstance(self.text, BaseText):  # pragma: no cover
                    raise
            return self.validate_dependency(param, self.plain_text, **kwds)
        elif param.name == "raw_text":
            try:
                return self.validate_dependency(param, self.raw_text, **kwds)
            except KaruhaHandlerInvokerError:
                if not isinstance(self.raw_text, Drafty):
                    raise
            return self.validate_dependency(param, self.raw_text.txt, **kwds)
        return super().get_dependency(param, **kwds)

    @computed_field(repr=False)
    @property
    def plain_text(self) -> str:
        return str(self.text)

    @computed_field(repr=False, return_type="Message")
    @property
    def message(self) -> Self:
        return self

    @computed_field(repr=False)
    @property
    def session(self) -> "MessageSession":
        return MessageSession(self.bot, self).bind_task()


from ..session import MessageSession


T = TypeVar("T")


if TYPE_CHECKING:
    Head = Annotated[T, ...]
else:

    class Head(HandlerInvokerDependency):
        __slots__ = []

        @classmethod
        def resolve_dependency(cls, invoker: Message, param: Parameter, **kwds: Any) -> Any:
            if not isinstance(invoker, Message):
                raise KaruhaHandlerInvokerError(f"cannot resolve head dependency for {param.name!r}")
            return invoker.head.get(param.name)

        def __class_getitem__(cls, tp: Type) -> Annotated:
            return Annotated[tp, cls()]
