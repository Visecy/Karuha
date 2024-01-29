from typing import Optional

from . import bot


class KaruhaException(Exception):
    """base exception for all errors in Karuha module"""
    __slots__ = []


class KaruhaBotError(KaruhaException):
    """unspecified chatbot run-time error"""
    __slots__ = ["bot"]

    def __init__(self, *args: object, bot: Optional["bot.Bot"] = None) -> None:
        super().__init__(*args)
        self.bot = bot


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
    def command(self) -> Optional["AbstractCommand"]:
        if self._command is not None:
            return self._command
        elif self.collection is not None:
            return self.collection.commands.get(self.name)


class KaruhaParserError(KaruhaException):
    """param parser error"""
    __slots__ = []


from .command.command import AbstractCommand
from .command.collection import CommandCollection
