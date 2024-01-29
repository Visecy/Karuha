from abc import ABC, abstractmethod
from typing import Dict, Iterable, Optional

from ..event.message import Message
from .parser import AbstractCommandNameParser
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
        else:
            raise ValueError(f"command {name} is not registered")
