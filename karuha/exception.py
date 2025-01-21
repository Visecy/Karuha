import asyncio
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .bot import Bot
    from .command.collection import CommandCollection
    from .command.command import AbstractCommand


class KaruhaException(Exception):
    """base exception for all errors in Karuha module"""
    __slots__ = []


class KaruhaServerError(KaruhaException):
    """unspecified server error"""
    __slots__ = []


class KaruhaBotError(KaruhaException):
    """unspecified chatbot error"""
    __slots__ = ["bot", "code"]

    def __init__(self, *args: object, bot: Optional["Bot"] = None, code: Optional[int] = None) -> None:
        super().__init__(*args)
        self.bot = bot
        self.code = code


class KaruhaRuntimeError(KaruhaException):
    """unspecified run-time error"""
    __slots__ = []


class KaruhaTimeoutError(KaruhaRuntimeError, asyncio.TimeoutError):
    """run-time error: timeout"""
    __slots__ = []


class KaruhaCommandError(KaruhaException):
    """command error"""
    __slots__ = ["name", "collection", "_command"]

    def __init__(
            self,
            *args: object,
            name: str,
            collection: Optional["CommandCollection"] = None,
            command: Optional["AbstractCommand"] = None
    ) -> None:
        super().__init__(*args)
        self.name = name
        self.collection = collection
        self._command = command
    
    @property
    def command(self):
        if self._command is not None:
            return self._command
        elif self.collection is not None:
            return self.collection.commands.get(self.name)


class KaruhaCommandCanceledError(asyncio.CancelledError):
    """command cancelled"""
    __slots__ = []


class KaruhaHandlerInvokerError(KaruhaException):
    """param parser error"""
    __slots__ = []
