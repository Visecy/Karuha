import asyncio
from abc import ABC, abstractmethod
from types import TracebackType
from typing import ClassVar, Generic, Set, Type, TypeVar
from typing_extensions import Self


T = TypeVar("T")


class AbstractDispatcher(ABC, Generic[T]):
    __slots__ = ["once"]

    dispatchers: ClassVar[Set[Self]] = set()

    def __init__(self, *, once: bool = False) -> None:
        self.once = once

    def match(self, message: T, /) -> float:
        """calculate the match for a given message

        Matching degree is divided into the following levels:

        1. 0~1: Weak priority, the lower dispatcher should return a value within this range
        2. 1~2: Normal matching, the regular dispatcher should return the value in this district level range
        3. 2~3: Specific matching, the dispatcher added only to process\
            specific transactions should return the value in this range
        4. 3~5: Urgent matters. Only dispatchers that need to handle special urgent matters\
            should return the value in this range.
        
        In principle, only values within the above range should be returned,
        but there are no specific restrictions on this.

        :param message: given message
        :type message: T
        :return: Matching degree
        :rtype: float
        """
        return 1
    
    @abstractmethod
    def run(self, message: T, /) -> None:
        raise NotImplementedError
    
    def activate(self) -> None:
        self.dispatchers.add(self)
    
    def deactivate(self) -> None:
        self.dispatchers.discard(self)
    
    @classmethod
    def dispatch(cls, message: T, /) -> None:
        if not cls.dispatchers:
            return
        selected = max(
            cls.dispatchers,
            key=lambda i: i.match(message)
        )
        if selected.once:
            selected.deactivate()
        selected.run(message)
    
    def __enter__(self) -> Self:
        self.activate()
        return self
    
    def __exit__(self, exec_type: Type[BaseException], exec_ins: BaseException, traceback: TracebackType) -> None:
        self.deactivate()
    
    @property
    def activated(self) -> bool:
        return self in self.dispatchers


class FutureDispatcher(AbstractDispatcher[T]):
    __slots__ = ["future"]

    def __init__(self, /, future: asyncio.Future, *, once: bool = False) -> None:
        super().__init__(once=once)
        self.future = future

    def run(self, message: T, /) -> None:
        self.future.set_result(message)
