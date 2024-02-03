import asyncio
from abc import ABC, abstractmethod
from inspect import signature
import sys
from typing import Any, Callable, Generic, Iterable, Optional, Tuple, TypeVar
from typing_extensions import Self, ParamSpec
from venv import logger

from ..exception import KaruhaCommandCanceledError, KaruhaCommandError

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
    async def call_command(self, collection: "CommandCollection", message: Message) -> Any:
        pass


class FunctionCommand(AbstractCommand, Generic[P, R]):
    __slots__ = ["__func__"]

    def __init__(self, name: str, func: Callable[P, R], /, alias: Optional[Iterable[str]] = None) -> None:
        super().__init__(name, alias)
        self.__func__ = func
    
    def parse_message(self, message: Message) -> Tuple[tuple, dict]:  # pragma: no cover
        return (self, message), {}
    
    async def call_command(self, collection: "CommandCollection", message: Message) -> Any:
        logger.debug(f"preparing command {self.name}")
        prepare_event = CommandPrepareEvent(collection, self, message)
        try:
            await prepare_event.trigger()
        except KaruhaCommandCanceledError:
            logger.info(f"command {self.name} canceled")
            raise
        try:
            args, kwargs = self.parse_message(message)
            result = self.__func__(*args, **kwargs)  # type: ignore
            if asyncio.iscoroutine(result):
                result = await result
        except Exception as e:  # pragma: no cover
            CommandFailEvent.new(collection, self, sys.exc_info())  # type: ignore
            logger.error(f"run command {self.name} failed", exc_info=True)
            raise KaruhaCommandError(f"run command {self.name} failed", name=self.name, command=self) from e
        else:
            logger.info(f"command {self.name} complete")
            CommandCompleteEvent.new(collection, self, result)
        return result
    
    def __call__(self, *args: P.args, **kwds: P.kwargs) -> R:
        return self.__func__(*args, **kwds)
    
    @classmethod
    def from_function(cls, /, func: Callable, *, name: Optional[str] = None, alias: Optional[Iterable[str]] = None) -> Self:
        if name is None:  # pragma: no cover
            name = func.__name__
        return cls(name, func, alias=alias)


class ParamFunctionCommand(FunctionCommand[P, R]):
    __slots__ = ["parser"]

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
        if name is None:  # pragma: no cover
            name = func.__name__
        sig = signature(func)
        parser = ParamParser.from_signature(sig, flags=flags)
        return cls(name, func, parser, alias=alias)


from .collection import CommandCollection
from ..event.command import CommandPrepareEvent, CommandCompleteEvent, CommandFailEvent
