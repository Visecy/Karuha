import asyncio
from abc import ABC, abstractmethod
from typing import ClassVar, Generic, Set, TypeVar
from typing_extensions import Self


T = TypeVar("T")


class AbstractDispatcher(ABC, Generic[T]):
    __slots__ = []

    dispatchers: ClassVar[Set[Self]] = set()

    def match(self, message: T, /) -> float:
        return 1
    
    @abstractmethod
    def run(self, message: T, /) -> None:
        raise NotImplementedError
    
    def activate(self) -> None:
        self.dispatchers.add(self)
    
    def deactivate(self) -> None:
        self.dispatchers.remove(self)
    
    @classmethod
    def dispatch(cls, message: T) -> None:
        if not cls.dispatchers:
            return
        selected = max(
            cls.dispatchers,
            key=lambda i: i.match(message)
        )
        selected.deactivate()
        selected.run(message)
    
    @property
    def activated(self) -> bool:
        return self in self.dispatchers


class FutureDispatcher(AbstractDispatcher[T]):
    __slots__ = ["future"]

    def __init__(self, future: asyncio.Future) -> None:
        super().__init__()
        self.future = future

    def run(self, message: T) -> None:
        self.future.set_result(message)
