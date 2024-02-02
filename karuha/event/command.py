from types import TracebackType
from typing import Any, Tuple, Type

from .. import event
from .base import Event
from ..text import Message


class BaseCommandEvent(Event):
    __slots__ = ["collection"]

    def __init__(self, collection: "CommandCollection") -> None:
        self.collection = collection


class CommandNotFoundEvent(BaseCommandEvent):
    __slots__ = ["command_name"]

    def __init__(self, collection: "CommandCollection", command_name: str) -> None:
        super().__init__(collection)
        self.command_name = command_name


class CommandEvent(BaseCommandEvent):
    __slots__ = ["command"]

    def __init__(self, collection: "CommandCollection", command: "AbstractCommand") -> None:
        super().__init__(collection)
        self.command = command


class CommandPrepareEvent(CommandEvent):
    __slots__ = ["message"]

    def __init__(self, collection: "CommandCollection", command: "AbstractCommand", message: Message) -> None:
        super().__init__(collection, command)
        self.message = message


class CommandCompleteEvent(CommandEvent):
    __slots__ = ["result"]

    def __init__(self, collection: "CommandCollection", command: "AbstractCommand", result: Any) -> None:
        super().__init__(collection, command)
        self.result = result


class CommandFailEvent(CommandEvent):
    __slots__ = ["exc_info"]

    def __init__(
            self,
            collection: "CommandCollection",
            command: "AbstractCommand",
            exc_info: Tuple[Type[BaseException], BaseException, TracebackType]
    ) -> None:
        super().__init__(collection, command)
        self.exc_info = exc_info


from ..command.command import AbstractCommand
from ..command.collection import CommandCollection

event.BaseCommandEvent = BaseCommandEvent  # type: ignore
event.CommandEvent = CommandEvent  # type: ignore
event.CommandNotFoundEvent = CommandNotFoundEvent  # type: ignore
event.CommandPrepareEvent = CommandPrepareEvent  # type: ignore
event.CommandCompleteEvent = CommandCompleteEvent  # type: ignore
event.CommandFailEvent = CommandFailEvent  # type: ignore
