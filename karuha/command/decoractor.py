from typing import Any, Callable, Iterable, Optional, TypeVar, Union, overload
from typing_extensions import ParamSpec

from .collection import CommandCollection, get_collection
from .command import FunctionCommand
from .parser import ParamParserFlag


P = ParamSpec("P")
R = TypeVar("R")


@overload
def on_command(
    name: Optional[str] = ...,
    /, *,
    alias: Optional[Iterable[str]] = ...,
    flags: ParamParserFlag = ...,
    collection: Optional[CommandCollection] = ...,
) -> Callable[[Callable[P, R]], FunctionCommand[P, R]]: ...


@overload
def on_command(
    func: Callable,
    /, *,
    alias: Optional[Iterable[str]] = ...,
    flags: ParamParserFlag = ...,
    collection: Optional[CommandCollection] = ...,
) -> FunctionCommand: ...


def on_command(
        func_or_name: Union[str, Callable[P, R], None] = None,
        /, *,
        collection: Optional[CommandCollection] = None,
        **kwds: Any
) -> Union[Callable, FunctionCommand[P, R]]:
    collection = collection or get_collection()
    return collection.on_command(func_or_name, **kwds)
