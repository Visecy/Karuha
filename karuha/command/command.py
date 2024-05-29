import asyncio
import sys
from abc import ABC, abstractmethod
from inspect import signature
from typing import Any, Callable, Generic, Iterable, Optional, Tuple, TypeVar
from venv import logger

from typing_extensions import ParamSpec, Self

from ..event.message import Message
from ..exception import KaruhaCommandCanceledError, KaruhaCommandError
from .rule import BaseRule


P = ParamSpec("P")
R = TypeVar("R")


class AbstractCommand(ABC):
    def __init__(self, name: str, /, alias: Optional[Iterable[str]] = None, *, rule: Optional[BaseRule] = None) -> None:
        self.__name__ = name
        self.rule = rule
        self.alias = () if alias is None else tuple(alias)
    
    @property
    def name(self) -> str:
        return self.__name__
    
    @abstractmethod
    async def call_command(self, message: "CommandMessage") -> Any:
        pass

    def format_help(self) -> str:
        if not self.alias:
            return self.name
        return f"{self.name} (alias: {','.join(self.alias)})"


class FunctionCommand(AbstractCommand, Generic[P, R]):
    def __init__(
        self,
        name: str,
        func: Callable[P, R],
        /,
        alias: Optional[Iterable[str]] = None,
        *,
        rule: Optional[BaseRule] = None,
    ) -> None:
        super().__init__(name, alias, rule=rule)
        self.__func__ = func
        self.__doc__ = getattr(func, "__doc__", None)
        self.__signature__ = signature(func)

    def parse_message(self, message: Message) -> Tuple[tuple, dict]:  # pragma: no cover
        args, kwargs = message.extract_handler_params(self.__signature__, name=self.name)
        return tuple(args), kwargs

    async def call_command(self, message: "CommandMessage") -> Any:
        logger.debug(f"preparing command {self.name}")
        prepare_event = CommandPrepareEvent(message.collection, self, message)
        try:
            await prepare_event.trigger()
        except KaruhaCommandCanceledError:
            logger.info(f"command {self.name} canceled before run")
            raise
        
        try:
            args, kwargs = self.parse_message(message)
            result = self.__func__(*args, **kwargs)  # type: ignore
            if asyncio.iscoroutine(result):
                result = await result
        except KaruhaCommandCanceledError as e:
            logger.info(f"command {self.name} canceled")
            CommandCompleteEvent.new(message.collection, self, e, cancelled=True)
            return
        except Exception as e:  # pragma: no cover
            logger.error(f"run command {self.name} failed", exc_info=True)
            CommandFailEvent.new(message.collection, self, sys.exc_info())  # type: ignore
            raise KaruhaCommandError(f"run command {self.name} failed", name=self.name, command=self) from e
        except asyncio.CancelledError:
            logger.info(f"command {self.name} canceled")
            CommandCompleteEvent.new(message.collection, self, None, cancelled=True)
            raise
        else:
            logger.info(f"command {self.name} complete")
            CommandCompleteEvent.new(message.collection, self, result)
        return result
    
    def format_help(self) -> str:
        if self.__doc__ is None:
            return super().format_help()
        if not self.alias:
            return f"{self.name} - {self.__doc__.strip()}"
        return f"{self.name} (alias: {','.join(self.alias)}) - {self.__doc__.strip()}"

    def __call__(self, *args: P.args, **kwds: P.kwargs) -> R:
        return self.__func__(*args, **kwds)

    @classmethod
    def from_function(
        cls,
        /,
        func: Callable,
        *,
        name: Optional[str] = None,
        alias: Optional[Iterable[str]] = None,
        rule: Optional[BaseRule] = None,
    ) -> Self:
        if name is None:  # pragma: no cover
            name = func.__name__
        return cls(name, func, alias=alias, rule=rule)


ParamFunctionCommand = FunctionCommand


from ..event.command import (CommandCompleteEvent, CommandFailEvent,
                             CommandPrepareEvent)
from .session import CommandMessage
