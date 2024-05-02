import asyncio
from typing import Optional

from .bot import Bot
from .command.collection import CommandCollection as CommandCollection
from .command.command import AbstractCommand as AbstractCommand


class KaruhaException(Exception):
    """base exception for all errors in Karuha module"""

class KaruhaRuntimeError(KaruhaException):
    """unspecified run-time error"""

class KaruhaBotError(KaruhaException):
    """unspecified chatbot run-time error"""

    bot: Optional[Bot]
    code: Optional[int]
    def __init__(
        self, *args: object, bot: Bot | None = None, code: int | None = None
    ) -> None: ...

class KaruhaTimeoutError(KaruhaRuntimeError, asyncio.TimeoutError):
    """run-time error: timeout"""

class KaruhaCommandError(KaruhaException):
    """command error"""

    name: str
    collection: Optional[CommandCollection]
    _command: Optional[AbstractCommand]

    def __init__(
        self,
        *args: object,
        name: str,
        collection: CommandCollection | None = None,
        command: AbstractCommand | None = None
    ) -> None: ...
    @property
    def command(self) -> AbstractCommand | None: ...

class KaruhaCommandCanceledError(asyncio.CancelledError):
    """command cancelled"""

class KaruhaHandlerInvokerError(KaruhaException):
    """param parser error"""
