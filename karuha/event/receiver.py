from abc import ABC, abstractmethod
from typing import Set

from .message import MessageEvent


class AbstractReceiver(ABC):
    __slots__ = []

    def match(self, message: MessageEvent) -> float:
        return 1
    
    @abstractmethod
    async def run(self, message: MessageEvent) -> None:
        raise NotImplementedError
    
    def activate(self) -> None:
        _receivers.add(self)
    
    def deactivate(self) -> None:
        _receivers.remove(self)
    
    @property
    def activated(self) -> bool:
        return self in _receivers


_receivers: Set[AbstractReceiver] = set()


@MessageEvent.add_handler
async def _(event: MessageEvent) -> None:
    selected = max(_receivers, key=lambda i: i.match(event))
    selected.deactivate()
    await selected.run(event)
