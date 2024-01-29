from typing import Any, Callable, Iterable, Optional, TypeVar, Union, overload
from typing_extensions import ParamSpec

from .collection import CommandCollection, get_default_collection
from .command import ArgparserFunctionCommand, FunctionCommand
from .parser import ParamParserFlag


P = ParamSpec("P")
R = TypeVar("R")


@overload
def on_command(
    name: str,
    /, *,
    alias: Optional[Iterable[str]] = ...,
    flags: ParamParserFlag = ...
) -> Callable[[Callable[P, R]], FunctionCommand[P, R]]: ...


@overload
def on_command(
    func: Callable,
    /, *,
    alias: Optional[Iterable[str]] = ...,
    flags: ParamParserFlag = ...
) -> FunctionCommand: ...


def on_command(
        func_or_name: Union[str, Callable[P, R]],
        /, *,
        flags: ParamParserFlag = ParamParserFlag.FULL,
        collection: Optional[CommandCollection] = None,
        **kwds: Any
) -> Union[Callable, FunctionCommand[P, R]]:
    collection = collection or get_default_collection()
    
    def inner(func: Callable[P, R]) -> FunctionCommand[P, R]:
        if isinstance(func_or_name, str):
            name = func_or_name
            func = func
        else:
            name = func.__name__
        if flags == ParamParserFlag.NONE:
            cmd = FunctionCommand(name, func, **kwds)
        else:
            cmd = ArgparserFunctionCommand.from_function(func, name=name, flags=flags, **kwds)
        collection.register_command(cmd)
        return cmd
    if isinstance(func_or_name, str):
        return inner
    return inner(func_or_name)
