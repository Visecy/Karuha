import re
from typing import Any, Callable, Generic, Iterable, Optional, TypeVar, Union, overload
from typing_extensions import ParamSpec

from ..bot import Bot
from ..text.message import Message
from .rule import BaseRule, MessageRuleDispatcher, rule as build_rule
from .collection import CommandCollection, get_collection
from .command import FunctionCommand


P = ParamSpec("P")
R = TypeVar("R")


@overload
def on_command(
    name: Optional[str] = ...,
    /, *,
    alias: Optional[Iterable[str]] = ...,
    collection: Optional[CommandCollection] = ...,
    rule: Optional[BaseRule] = ...
) -> Callable[[Callable[P, R]], FunctionCommand[P, R]]: ...


@overload
def on_command(
    func: Callable,
    /, *,
    alias: Optional[Iterable[str]] = ...,
    collection: Optional[CommandCollection] = ...,
    rule: Optional[BaseRule] = ...
) -> FunctionCommand: ...


def on_command(
        func_or_name: Union[str, Callable[P, R], None] = None,
        /, *,
        collection: Optional[CommandCollection] = None,
        **kwds: Any
) -> Union[Callable, FunctionCommand[P, R]]:
    collection = collection or get_collection()
    return collection.on_command(func_or_name, **kwds)


class _RuleDispatcherWrapper(MessageRuleDispatcher, Generic[P, R]):
    __slots__ = ["__wrapped__"]

    def __init__(self, rule: BaseRule, func: Callable[P, R], *, once: bool = False, weights: float = 1.5) -> None:
        super().__init__(rule, once=once, weights=weights)
        self.__wrapped__ = func
    
    def __call__(self, *args: P.args, **kwds: P.kwargs) -> R:
        return self.__wrapped__(*args, **kwds)
    
    def run(self, message: Message) -> R:
        return message.call_handler(self.__wrapped__)


@overload
def on_rule(
        rule: BaseRule,
        *,
        once: bool = False,
        weights: float = 1.5,
) -> Callable[[Callable[P, R]], _RuleDispatcherWrapper[P, R]]:
    ...


@overload
def on_rule(
        *,
        once: bool = False,
        weights: float = 1.5,
        topic: Optional[str] = None,
        seq_id: Optional[int] = None,
        user_id: Optional[str] = None,
        bot: Optional[Bot] = None,
        keyword: Optional[str] = None,
        regex: Optional[Union[str, re.Pattern]] = None,
        mention: Optional[str] = None,
        to_me: bool = False,
        quote: Optional[Union[int, bool]] = None,
) -> Callable[[Callable[P, R]], _RuleDispatcherWrapper[P, R]]:
    ...


def on_rule(
        rule: Optional[BaseRule] = None,
        *,
        once: bool = False,
        weights: float = 1.5,
        **kwds: Any
) -> Callable[[Callable[P, R]], _RuleDispatcherWrapper[P, R]]:
    def wrapper(func: Callable[P, R], /) -> _RuleDispatcherWrapper[P, R]:
        if rule is None:
            r = build_rule(**kwds)
        else:
            assert not kwds, "rule and kwds cannot be used together"
            r = rule
        dispatcher = _RuleDispatcherWrapper(r, func, once=once, weights=weights)
        dispatcher.activate()
        return dispatcher
    return wrapper
