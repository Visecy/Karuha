from inspect import Parameter
from typing import Any, Deque, Iterable, NoReturn, Tuple, Union
from pydantic import computed_field
from typing_extensions import Self

from ..session import BaseSession  # noqa: F401
from ..text import BaseText
from ..text.message import Message, MessageSession
from ..exception import KaruhaCommandCanceledError, KaruhaHandlerInvokerError


class CommandMessage(Message, frozen=True, arbitrary_types_allowed=True):
    name: str
    argv: Tuple[Union[str, BaseText], ...]
    command: "AbstractCommand"
    collection: "CommandCollection"

    @classmethod
    def from_message(
            cls,
            message: Message,
            /,
            command: "AbstractCommand",
            collection: "CommandCollection",
            name: str,
            argv: Iterable[Union[str, BaseText]]
    ) -> Self:
        data = dict(message)
        data["command"] = command
        data["collection"] = collection
        data["name"] = name
        data["argv"] = tuple(argv)
        return cls(**data)
    
    def get_dependency(self, param: Parameter) -> Any:
        if param.name == "argv":
            try:
                return self.validate_dependency(param, self.argv)
            except KaruhaHandlerInvokerError:
                pass
            return self.validate_dependency(param, tuple(str(i) for i in self.argv))
        return super().get_dependency(param)
    
    @computed_field
    @property
    def argc(self) -> int:
        return len(self.argv)
    
    @computed_field
    @property
    def session(self) -> "CommandSession":
        return CommandSession(self.bot, self)


class CommandSession(MessageSession):
    __slots__ = []

    _messages: Deque["CommandMessage"]

    def cancel(self) -> NoReturn:
        raise KaruhaCommandCanceledError
    
    @property
    def messages(self) -> Tuple["CommandMessage", ...]:
        return tuple(self._messages)
    
    @property
    def last_message(self) -> "CommandMessage":
        return self._messages[-1]


from .command import AbstractCommand
from .collection import CommandCollection
