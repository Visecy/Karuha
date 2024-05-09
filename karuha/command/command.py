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
    __slots__ = ["__name__", "alias", "rule"]

    def __init__(self, name: str, /, alias: Optional[Iterable[str]] = None, *, rule: Optional[BaseRule] = None) -> None:
        self.__name__ = name
        self.rule = rule
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
    __slots__ = ["__func__", "__signature__"]

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
        self.__signature__ = signature(func)

    def parse_message(self, message: Message) -> Tuple[tuple, dict]:  # pragma: no cover
        args, kwargs = message.extract_handler_params(self.__signature__)
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
        except KaruhaCommandCanceledError:
            logger.info(f"command {self.name} canceled")
            return
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
