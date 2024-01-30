import asyncio
from abc import ABC, abstractmethod
from inspect import signature
from typing import Any, Callable, Generic, Iterable, Optional, Tuple, TypeVar
from typing_extensions import Self, ParamSpec

from ..exception import KaruhaCommandError

from ..event.message import Message
from .parser import ParamParser, ParamParserFlag


P = ParamSpec("P")
R = TypeVar("R")


class AbstractCommand(ABC):
    __slots__ = ["__name__", "alias"]

    def __init__(self, name: str, /, alias: Optional[Iterable[str]] = None) -> None:
        self.__name__ = name
        if alias is None:
            self.alias = ()
        else:
            self.alias = tuple(alias)
    
    @property
    def name(self) -> str:
        return self.__name__
    
    @abstractmethod
    async def call_command(self, message: Message) -> Any:
        pass


class FunctionCommand(AbstractCommand, Generic[P, R]):
    __slots__ = ["name", "alias", "__func__"]

    def __init__(self, name: str, func: Callable[P, R], /, alias: Optional[Iterable[str]] = None) -> None:
        super().__init__(name, alias)
        self.__func__ = func
    
    def parse_message(self, message: Message) -> Tuple[tuple, dict]:
        return (self, message), {}
    
    async def call_command(self, message: Message) -> Any:
        args, kwargs = self.parse_message(message)
        try:
            result = self.__func__(*args, **kwargs)  # type: ignore
            if asyncio.iscoroutine(result):
                result = await result
        except Exception as e:  # pragma: no cover
            raise KaruhaCommandError(f"run command {self.name} failed", name=self.name, command=self) from e
        return result
    
    def __call__(self, *args: P.args, **kwds: P.kwargs) -> R:
        return self.__func__(*args, **kwds)
    
    @classmethod
    def from_function(cls, /, func: Callable, *, name: Optional[str] = None, alias: Optional[Iterable[str]] = None) -> Self:
        if name is None:
            name = func.__name__
        return cls(name, func, alias=alias)


class ParamFunctionCommand(FunctionCommand[P, R]):
    __slots__ = ["name", "alias", "__func__", "parser"]

    def __init__(self, name: str, func: Callable[P, R], parser: ParamParser, /, alias: Optional[Iterable[str]] = None) -> None:
        super().__init__(name, func, alias)
        self.parser = parser
    
    def parse_message(self, message: Message) -> Tuple[tuple, dict]:
        return self.parser.parse(message)
    
    @classmethod
    def from_function(
            cls,
            /,
            func: Callable[P, R],
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
