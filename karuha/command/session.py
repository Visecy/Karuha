from typing import Deque, NoReturn, Tuple

from ..session import BaseSession  # noqa: F401
from ..text import MessageSession
from ..exception import KaruhaCommandCanceledError


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


from .command import CommandMessage
