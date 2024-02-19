import asyncio
import sys
from abc import ABC, abstractmethod
from inspect import signature
from typing import Any, Callable, Generic, Iterable, Optional, Tuple, TypeVar, Union
from venv import logger

from typing_extensions import ParamSpec, Self

from ..text.textchain import BaseText
from ..event.message import Message
from ..exception import KaruhaCommandCanceledError, KaruhaCommandError


P = ParamSpec("P")
R = TypeVar("R")


class CommandMessage(Message, frozen=True, arbitrary_types_allowed=True):
    name: str
    argv: Tuple[Union[str, BaseText], ...]
    command: "AbstractCommand"
    collection: "CommandCollection"

    @classmethod
    def from_message(
            cls,
            message: Message,
            /,
            command: "AbstractCommand",
            collection: "CommandCollection",
            name: str,
            argv: Iterable[Union[str, BaseText]]
    ) -> Self:
        data = dict(message)
        data["command"] = command
        data["collection"] = collection
        data["name"] = name
        data["argv"] = tuple(argv)
        return cls(**data)


from .parser import ParamParser, ParamParserFlag


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
    async def call_command(self, message: "CommandMessage") -> Any:
        pass


class FunctionCommand(AbstractCommand, Generic[P, R]):
    __slots__ = ["__func__"]

    def __init__(self, name: str, func: Callable[P, R], /, alias: Optional[Iterable[str]] = None) -> None:
        super().__init__(name, alias)
        self.__func__ = func
    
    def parse_message(self, message: Message) -> Tuple[tuple, dict]:  # pragma: no cover
        return (self, message), {}
    
    async def call_command(self, message: "CommandMessage") -> Any:
        logger.debug(f"preparing command {self.name}")
        prepare_event = CommandPrepareEvent(message.collection, self, message)
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
            CommandFailEvent.new(message.collection, self, sys.exc_info())  # type: ignore
            logger.error(f"run command {self.name} failed", exc_info=True)
            raise KaruhaCommandError(f"run command {self.name} failed", name=self.name, command=self) from e
        else:
            logger.info(f"command {self.name} complete")
            CommandCompleteEvent.new(message.collection, self, result)
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
    
    def parse_message(self, message: "CommandMessage") -> Tuple[tuple, dict]:
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


from ..event.command import (CommandCompleteEvent, CommandFailEvent,
                             CommandPrepareEvent)
from .collection import CommandCollection
