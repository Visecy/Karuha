from typing import Any, Callable, Generic, Iterable, Optional, TypeVar, Union, overload
from typing_extensions import ParamSpec

from ..text.message import Message
from .rule import BaseRule, MessageRuleDispatcher
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

    def __init__(self, rule: BaseRule, func: Callable[P, R], *, once: bool = False) -> None:
        super().__init__(rule, once=once)
        self.__wrapped__ = func
    
    def __call__(self, *args: P.args, **kwds: P.kwargs) -> R:
        return self.__wrapped__(*args, **kwds)
    
    def run(self, message: Message) -> Any:
        return message.call_handler(self.__wrapped__)


def on_rule(
        rule: BaseRule,
        *,
        once: bool = False
) -> Callable[[Callable[P, R]], _RuleDispatcherWrapper[P, R]]:
    def wrapper(func: Callable[P, R], /) -> _RuleDispatcherWrapper[P, R]:
        dispatcher = _RuleDispatcherWrapper(rule, func, once=once)
        dispatcher.activate()
        return dispatcher
    return wrapper
