import asyncio
from abc import ABC, abstractmethod
from inspect import signature
from typing import Any, Callable, Iterable, Optional, Tuple
from typing_extensions import Self

from ..event.message import Message
from .parser import ParamParser, ParamParserFlag


class AbstractCommand(ABC):
    __slots__ = ["name", "alias"]

    def __init__(self, name: str, /, alias: Optional[Iterable[str]] = None) -> None:
        self.name = name
        if alias is None:
            self.alias = ()
        else:
            self.alias = tuple(alias)
    
    @abstractmethod
    async def call_command(self, message: Message) -> Any:
        pass


class FunctionCommand(AbstractCommand):
    __slots__ = ["name", "alias", "__func__"]

    def __init__(self, name: str, func: Callable, /, alias: Optional[Iterable[str]] = None) -> None:
        super().__init__(name, alias)
        self.__func__ = func
    
    def parse_message(self, message: Message) -> Tuple[tuple, dict]:
        return (self, message), {}
    
    async def call_command(self, message: Message) -> Any:
        args, kwargs = self.parse_message(message)
        result = self.__func__(*args, **kwargs)
        if asyncio.iscoroutine(result):
            result = await result
        return result
    
    def __call__(self, *args: Any, **kwds: Any) -> Any:
        return self.__func__(*args, **kwds)
    
    @classmethod
    def from_function(cls, /, func: Callable, *, name: Optional[str] = None, alias: Optional[Iterable[str]] = None) -> Self:
        if name is None:
            name = func.__name__
        return cls(name, func, alias=alias)


class ArgparserFunctionCommand(FunctionCommand):
    __slots__ = ["name", "alias", "__func__", "parser"]

    def __init__(self, name: str, func: Callable, parser: ParamParser, /, alias: Optional[Iterable[str]] = None) -> None:
        super().__init__(name, func, alias)
        self.parser = parser
    
    def parse_message(self, message: Message) -> Tuple[tuple, dict]:
        return self.parser.parse(message)
    
    @classmethod
    def from_function(
            cls,
            /,
            func: Callable,
            *,
            name: Optional[str] = None,
            alias: Optional[Iterable[str]] = None,
            flags: ParamParserFlag = ParamParserFlag.FULL
    ) -> Self:
        if name is None:
            name = func.__name__
        sig = signature(func)
        parser = ParamParser.from_signature(sig, flags=flags)
        return cls(name, func, parser, alias=alias)
