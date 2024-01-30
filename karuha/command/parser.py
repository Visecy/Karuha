from abc import ABC, abstractmethod
from enum import IntFlag
from functools import partial
from inspect import Signature, Parameter
from typing import Any, Callable, Iterable, NamedTuple, Optional, Tuple, Type, Union, get_args
from typing_extensions import Self

from ..utils.dispatcher import AbstractDispatcher
from ..text import Drafty, BaseText, Message
from ..exception import KaruhaParserError
from ..bot import Bot
from .session import MessageSession


class AbstractCommandNameParser(ABC):
    __slots__ = []

    @abstractmethod
    def parse(self, message: Message) -> Optional[str]:
        raise NotImplementedError

    def check_name(self, name: str) -> bool:
        return True


class SimpleCommandNameParser(AbstractCommandNameParser):
    __slots__ = ["prefixs"]

    def __init__(self, prefix: Iterable[str]) -> None:
        self.prefixs = tuple(prefix)
    
    def parse(self, message: Message) -> Optional[str]:
        if isinstance(message.raw_text, Drafty):
            text = message.raw_text.txt
        else:
            text = message.raw_text
        text = text.split(None, 1)
        if not text:
            return
        
        name = text[0]
        for prefix in self.prefixs:
            if name.startswith(prefix):
                return name[len(prefix):]
    
    def check_name(self, name: str) -> bool:
        return ' ' not in name


class ParamParserFlag(IntFlag):
    NONE = 0
    META = 1
    MESSAGE_DATA = 2
    SESSION = 4
    BOT = 8
    MESSAGE = 16

    FULL = META | MESSAGE_DATA | SESSION | BOT | MESSAGE


class ParamDispatcher(AbstractDispatcher[Parameter]):
    __slots__ = ["flag"]

    dispatchers = set()

    def __init__(self, /, flag: ParamParserFlag) -> None:
        super().__init__(once=False)
        self.flag = flag

        # auto activate
        self.activate()

    @classmethod
    def dispatch(cls, message: Parameter, /, threshold: float = 0.6, flag: ParamParserFlag = ParamParserFlag.FULL) -> Any:
        return super().dispatch(message, threshold, filter=lambda d: d.flag & flag != 0)
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} flag={self.flag}>"
    

RawParamGetter = Callable[["MetaParamDispatcher", Message], Any]
ParamGetter = Callable[[Message], Any]


class MetaParamDispatcher(ParamDispatcher):
    __slots__ = ["name", "type", "type_args", "raw_getter", "flag", "special_type"]

    def __init__(
            self,
            name: str,
            /,
            type: Type,
            getter: RawParamGetter,
            flag: ParamParserFlag = ParamParserFlag.NONE,
            special_type: bool = False
    ) -> None:
        super().__init__(flag=flag)
        self.name = name
        self.type = type
        self.type_args = set(get_args(type))
        self.raw_getter = getter
        self.special_type = special_type
    
    def match(self, parameter: Parameter, /) -> float:
        rate = 0.0
        if parameter.name == self.name:
            if parameter.kind == Parameter.KEYWORD_ONLY:
                rate += 1.2
            else:
                rate += 1.0
        if parameter.annotation == self.type:
            if self.special_type:
                rate += 1.0
            else:
                rate += 0.4
        elif parameter.annotation == Any:
            pass
        elif self.type in get_args(parameter.annotation) or set(get_args(parameter.annotation)) & self.type_args:
            if self.special_type:
                rate += 0.5
            else:
                rate += 0.2
        elif parameter.annotation != Parameter.empty:
            rate -= 0.4
        return rate
    
    def run(self, param: Parameter, /) -> ParamGetter:
        return partial(self.raw_getter, self)
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} type={self.type} flag={self.flag}>"


class ParamParser(NamedTuple):
    args: Tuple[ParamGetter, ...]
    kwargs: Tuple[Tuple[str, ParamGetter], ...]
    flags: ParamParserFlag = ParamParserFlag.FULL

    @classmethod
    def from_signature(cls, signature: Signature, *, flags: ParamParserFlag = ParamParserFlag.FULL) -> Self:
        args = []
        kwargs = {}
        for name, param in signature.parameters.items():
            dispatcher = ParamDispatcher.dispatch(param, flag=flags)
            if dispatcher is None:
                raise KaruhaParserError(f"cannot find a dispatcher for {param} in {signature}")
            elif param.kind == Parameter.POSITIONAL_ONLY:
                args.append(dispatcher)
            elif param.kind in [Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD]:
                raise KaruhaParserError(f"unexpected parameter kind {param.kind} in {signature}")
            else:
                kwargs[name] = dispatcher
        return cls(tuple(args), tuple(kwargs.items()), flags)
    
    def parse(self, message: Message) -> Tuple[Tuple[Any, ...], dict]:
        args = tuple(i(message) for i in self.args)
        kwargs = {k: v(message) for k, v in self.kwargs}
        return args, kwargs


MessageParamDispatcher = partial(
    MetaParamDispatcher,
    getter=lambda d, m: getattr(m, d.name),
    flag=ParamParserFlag.MESSAGE_DATA | ParamParserFlag.META
)


TOPIC_PARAM = MessageParamDispatcher("topic", type=str)
USER_ID_PARAM = MessageParamDispatcher("user_id", type=str)
SEQ_ID_PARAM = MessageParamDispatcher("seq_id", type=int)
HEAD_PARAM = MessageParamDispatcher("head", type=dict)

CONTENT_PARAM = MessageParamDispatcher("content", type=bytes)
TEXT_PARAM = MessageParamDispatcher("text", type=Union[str, BaseText])
RAW_TEXT_PARAM = MessageParamDispatcher("raw_text", type=Union[str, Drafty])

SESSION_PARAM = MetaParamDispatcher(
    "session",
    type=MessageSession,
    getter=lambda _, m: MessageSession(m.bot, m),
    flag=ParamParserFlag.SESSION | ParamParserFlag.META,
    special_type=True
)
BOT_PARAM = MetaParamDispatcher(
    "bot",
    type=Bot,
    getter=lambda _, m: m.bot,
    flag=ParamParserFlag.BOT | ParamParserFlag.META,
    special_type=True
)
MESSAGE_PARAM = MetaParamDispatcher(
    "message",
    type=Message,
    getter=lambda _, m: m,
    flag=ParamParserFlag.MESSAGE | ParamParserFlag.META,
    special_type=True
)
