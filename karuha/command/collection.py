from typing import Callable, Dict, Iterable, Optional

from ..exception import KaruhaCommandError

from ..event.message import Message
from .parser import AbstractCommandNameParser, SimpleCommandNameParser
from .command import AbstractCommand


class CommandCollection:
    __slots__ = ["commands", "name_parser"]

    commands: Dict[str, AbstractCommand]

    def __init__(self, /, name_parser: AbstractCommandNameParser) -> None:
        self.commands = {}
        self.name_parser = name_parser
    
    def register_command(self, command: AbstractCommand, /) -> None:
        if command.name in self.commands:
            raise ValueError(f"command {command.name} is already registered")
        self.commands[command.name] = command
        for alias in command.alias:
            if alias in self.commands:
                raise ValueError(f"command {alias} is already registered")
            self.commands[alias] = command
    
    async def run(self, message: Message) -> None:
        name = self.name_parser.parse(message)
        if name and name in self.commands:
            await self.commands[name].call_command(message)
        elif name:
            raise KaruhaCommandError(f"command {name} is not registered", name=name, collection=self)


_default_prefix = ('/',)
_default_collection: Optional[CommandCollection] = None


def get_default_collection() -> CommandCollection:
    global _default_collection
    if _default_collection is None:
        _default_collection = CommandCollection(SimpleCommandNameParser(["!"]))
    return _default_collection


def default_collection_factory() -> CommandCollection:
    return CommandCollection(
        SimpleCommandNameParser(_default_prefix)
    )


__default_collection_factory_backup = default_collection_factory


def set_prefix(prefix: Iterable[str]) -> None:
    global _default_prefix
    if _default_collection is not None or default_collection_factory is not __default_collection_factory_backup:
        raise RuntimeError("cannot set prefix after collection is created")
    _default_prefix = tuple(prefix)


def set_default_collection_factory(factory: Callable[[], CommandCollection]) -> None:
    global default_collection_factory
    if _default_collection is not None:
        raise RuntimeError("cannot set default collection factory after collection is created")
    default_collection_factory = factory
