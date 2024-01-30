import asyncio
from typing import Any, Callable, Dict, Iterable, Optional, TypeVar, Union, overload
from typing_extensions import ParamSpec

from ..utils.dispatcher import _ContextHelper
from ..text.message import Message
from ..event.message import MessageDispatcher, MessageEvent
from ..exception import KaruhaCommandError
from .parser import AbstractCommandNameParser, ParamParserFlag, SimpleCommandNameParser
from .command import AbstractCommand, ParamFunctionCommand, FunctionCommand


P = ParamSpec("P")
R = TypeVar("R")


class CommandCollection(_ContextHelper):
    __slots__ = ["commands", "name_parser", "_dispatcher"]

    commands: Dict[str, AbstractCommand]

    def __init__(self, /, name_parser: AbstractCommandNameParser) -> None:
        self.commands = {}
        self.name_parser = name_parser
        self._dispatcher = None
    
    def add_command(self, command: AbstractCommand, /) -> None:
        self._check_name(command.__name__)
        self.commands[command.__name__] = command
        for alias in command.alias:
            self._check_name(alias)
            self.commands[alias] = command
        
    @overload
    def on_command(
        self,
        name: Optional[str] = ...,
        /, *,
        alias: Optional[Iterable[str]] = ...,
        flags: ParamParserFlag = ...
    ) -> Callable[[Callable[P, R]], FunctionCommand[P, R]]: ...

    @overload
    def on_command(
        self,
        func: Callable[P, R],
        /, *,
        alias: Optional[Iterable[str]] = ...,
        flags: ParamParserFlag = ...
    ) -> FunctionCommand[P, R]: ...

    def on_command(
            self,
            func_or_name: Union[str, Callable[P, R], None] = None,
            /, *,
            flags: ParamParserFlag = ParamParserFlag.FULL,
            **kwds: Any
    ) -> Union[Callable[[Callable[P, R]], FunctionCommand[P, R]], FunctionCommand[P, R]]:
        def inner(func: Callable[P, R]) -> FunctionCommand[P, R]:
            if isinstance(func_or_name, str):
                name = func_or_name
            else:
                name = func.__name__
            if flags == ParamParserFlag.NONE:
                cmd = FunctionCommand.from_function(func, name=name, **kwds)
            else:
                cmd = ParamFunctionCommand.from_function(func, name=name, flags=flags, **kwds)
            self.add_command(cmd)
            return cmd
    
        if isinstance(func_or_name, str) or func_or_name is None:
            return inner
        return inner(func_or_name)
    
    async def run(self, message: Message) -> None:
        name = self.name_parser.parse(message)
        if name and name in self.commands:
            await self.commands[name].call_command(message)
        elif name:  # pragma: no cover
            raise KaruhaCommandError(f"command {name} is not registered", name=name, collection=self)
    
    def activate(self) -> None:
        if self._dispatcher is not None:
            return
        self._dispatcher = CommandDispatcher(self)
        self._dispatcher.activate()
    
    def deactivate(self) -> None:
        assert self._dispatcher is not None
        self._dispatcher.deactivate()
        self._dispatcher = None
    
    @property
    def activated(self) -> bool:
        return self._dispatcher is not None
    
    def _check_name(self, name: str) -> None:
        if name in self.commands:
            raise ValueError(f"command {name} is already registered")
        if not self.name_parser.check_name(name):
            raise ValueError(f"command {name} is not valid")
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} with {len(self.commands)} commands at 0x{id(self):016x}>"


class CommandDispatcher(MessageDispatcher):
    __slots__ = ["collection"]

    def __init__(self, collection: CommandCollection, *, once: bool = False) -> None:
        super().__init__(once=once)
        self.collection = collection
    
    def run(self, message: MessageEvent) -> asyncio.Task:
        return asyncio.create_task(self.collection.run(message.dump()))


_default_prefix = ('/',)
_default_collection: Optional[CommandCollection] = None


def get_collection() -> CommandCollection:
    global _default_collection
    if _default_collection is None:
        _default_collection = new_collection()
        _default_collection.activate()
    return _default_collection


def set_collection(collection: CommandCollection) -> None:
    global _default_collection
    if _default_collection is not None:
        _default_collection.deactivate()
    _default_collection = collection
    collection.activate()


def reset_collection() -> None:
    global _default_collection
    if _default_collection is None:
        return
    _default_collection.deactivate()
    _default_collection = None


def new_collection() -> CommandCollection:
    return CommandCollection(
        SimpleCommandNameParser(_default_prefix)
    )


__collection_factory_backup = new_collection


def set_prefix(*prefix: str) -> None:
    global _default_prefix
    if _default_collection is not None or new_collection is not __collection_factory_backup:
        raise RuntimeError("cannot set prefix after collection is created")
    elif not prefix:  # pragma: no cover
        raise ValueError("prefix must be at least one")
    _default_prefix = tuple(prefix)


def set_collection_factory(factory: Callable[[], CommandCollection], reset: bool = False) -> None:
    global new_collection, _default_collection
    if _default_collection is not None:
        if reset:
            reset_collection()
        else:
            raise RuntimeError("cannot set default collection factory after collection is created")
    new_collection = factory
