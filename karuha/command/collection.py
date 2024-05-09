import asyncio
import sys
from typing import Any, Callable, Dict, Generator, Iterable, List, Optional, Set, TypeVar, Union, overload
from typing_extensions import ParamSpec

from ..utils.context import _ContextHelper
from ..logger import logger
from ..text.message import Message
from ..exception import KaruhaCommandError, KaruhaException
from .parser import AbstractCommandParser, SimpleCommandParser
from .rule import BaseRule, MessageRuleDispatcher, NoopRule
from .command import AbstractCommand, FunctionCommand
from .session import CommandMessage


P = ParamSpec("P")
R = TypeVar("R")


class CommandCollection(_ContextHelper):
    __slots__ = ["commands", "name_parser", "sub_collections", "_dispatcher", "rule"]

    commands: Dict[str, AbstractCommand]
    sub_collections: List["CommandCollection"]

    def __init__(self, /, name_parser: AbstractCommandParser, *, rule: Optional[BaseRule] = None) -> None:
        self.commands = {}
        self.name_parser = name_parser
        self.sub_collections = []
        self._dispatcher = None
        self.rule = rule
    
    def add_command(self, command: AbstractCommand, /) -> None:
        self._check_name(command.__name__)
        self.commands[command.__name__] = command
        for alias in command.alias:
            self._check_name(alias)
            self.commands[alias] = command
    
    def get_command(self, name: str, default: Optional[AbstractCommand] = None, /) -> Optional[AbstractCommand]:
        for c in self._get_commands(name):
            return c
        return default
        
    @overload
    def on_command(
        self,
        name: Optional[str] = ...,
        /, *,
        alias: Optional[Iterable[str]] = ...,
        rule: Optional[BaseRule] = ...,
    ) -> Callable[[Callable[P, R]], FunctionCommand[P, R]]: ...

    @overload
    def on_command(
        self,
        func: Callable[P, R],
        /, *,
        alias: Optional[Iterable[str]] = ...,
        rule: Optional[BaseRule] = ...,
    ) -> FunctionCommand[P, R]: ...

    def on_command(
            self,
            func_or_name: Union[str, Callable[P, R], None] = None,
            /,
            **kwds: Any
    ) -> Union[Callable[[Callable[P, R]], FunctionCommand[P, R]], FunctionCommand[P, R]]:
        def inner(func: Callable[P, R]) -> FunctionCommand[P, R]:
            if isinstance(func_or_name, str):
                name = func_or_name
            else:
                name = func.__name__
            cmd = FunctionCommand.from_function(func, name=name, **kwds)
            self.add_command(cmd)
            return cmd
    
        if isinstance(func_or_name, str) or func_or_name is None:
            return inner
        return inner(func_or_name)
    
    async def run(self, message: Message) -> None:
        result = self.name_parser.parse(message)
        if result is None:
            return
        
        name, argv = result
        for command in self._get_commands(name):
            if command.rule is None or command.rule.match(message):
                break
        else:
            CommandNotFoundEvent.new(self, name)
            logger.error(f"command {name} not found")
            return
        
        try:
            await command.call_command(CommandMessage.from_message(message, command, self, name, argv))
        except KaruhaException:
            pass
        except Exception:  # pragma: no cover
            message.bot.logger.error(
                f"unexpected error while running command from message {message}",
                exc_info=sys.exc_info()
            )
    
    def activate(self) -> None:
        if self._dispatcher is not None:  # pragma: no cover
            return
        self._dispatcher = CommandDispatcher(self)
        self._dispatcher.activate()
    
    def deactivate(self) -> None:
        assert self._dispatcher is not None
        self._dispatcher.deactivate()
        self._dispatcher = None
    
    def __getitem__(self, name: str, /) -> AbstractCommand:
        command = self.get_command(name)
        if command is not None:
            return command
        raise KaruhaCommandError(f"command {name} is not registered", name=name, collection=self)
    
    @property
    def activated(self) -> bool:
        return self._dispatcher is not None
    
    def _get_commands(self, name: str, /) -> Generator[AbstractCommand, None, None]:
        if name in self.commands:
            yield self.commands[name]
        for i in self.sub_collections:
            yield from i._get_commands(name)
    
    def _check_name(self, name: str) -> None:
        if name in self.commands:
            raise ValueError(f"command {name} is already registered")
        if not self.name_parser.check_name(name):
            raise ValueError(f"command {name} is not valid")
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} with {len(self.commands)} commands at 0x{id(self):016x}>"


class CommandDispatcher(MessageRuleDispatcher):
    __slots__ = ["collection"]

    def __init__(self, collection: CommandCollection, *, once: bool = False) -> None:
        super().__init__(collection.rule or NoopRule(), 0.8, once=once)
        self.collection = collection
    
    def match(self, message: Message, /) -> float:
        if self.collection.name_parser.precheck(message):
            return super().match(message)
        return 0
    
    def run(self, message: Message) -> asyncio.Task:
        return asyncio.create_task(self.collection.run(message))


_default_prefix = ('/',)
_default_collection: Optional[CommandCollection] = None
_sub_collections: Set[CommandCollection] = set()


def get_collection(*args: Any, **kwds: Any) -> CommandCollection:
    global _default_collection
    if _default_collection is None:
        _default_collection = new_collection(*args, **kwds)
        _default_collection.activate()
        _default_collection.sub_collections.extend(_sub_collections)
    return _default_collection


def set_collection(collection: CommandCollection) -> None:
    global _default_collection
    if _default_collection is not None:
        _default_collection.deactivate()
    _default_collection = collection
    collection.activate()


def add_sub_collection(collection: CommandCollection) -> None:
    _sub_collections.add(collection)


def remove_sub_collection(collection: CommandCollection) -> None:
    _sub_collections.remove(collection)


def reset_collection() -> None:
    global _default_collection
    if _default_collection is None:
        return
    _default_collection.deactivate()
    _default_collection = None


def new_collection(*, rule: Optional[BaseRule] = None) -> CommandCollection:
    return CommandCollection(
        SimpleCommandParser(_default_prefix),
        rule=rule
    )


__collection_factory_backup = new_collection


def set_prefix(*prefix: str) -> None:
    global _default_prefix
    if _default_collection is not None or new_collection is not __collection_factory_backup:
        raise RuntimeError("cannot set prefix after collection is created")
    elif not prefix:  # pragma: no cover
        raise ValueError("prefix must be at least one")
    _default_prefix = prefix


def set_collection_factory(factory: Optional[Callable[..., CommandCollection]], reset: bool = False) -> None:
    global new_collection
    if _default_collection is not None:
        if reset:
            reset_collection()
        else:
            raise RuntimeError("cannot set default collection factory after collection is created")
    new_collection = factory or __collection_factory_backup


from ..event.command import CommandNotFoundEvent
