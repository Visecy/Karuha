import asyncio
from abc import ABC, abstractmethod
from typing import Any, Callable, ClassVar, Generic, Optional, Set, TypeVar
from typing_extensions import Self

from .context import _ContextHelper


T = TypeVar("T")


class AbstractDispatcher(_ContextHelper, Generic[T]):
    __slots__ = ["once"]

    dispatchers: ClassVar[Set[Self]] = set()

    def __init__(self, *, once: bool = False) -> None:
        self.once = once

    def match(self, message: T, /) -> float:  # pragma: no cover
        """calculate the match for a given message

        Matching degree is divided into the following levels:

        1. 0.4~1: Weak priority, the lower dispatcher should return a value within this range
        2. 1~2: Normal matching, the regular dispatcher should return the value in this district level range
        3. 2~3: Specific matching, the dispatcher added only to process\
            specific transactions should return the value in this range
        4. 3~5: Urgent matters. Only dispatchers that need to handle special urgent matters\
            should return the value in this range.
        
        In principle, only values within the above range should be returned.
        Values less than 0.4 will be ignored by default,
        while there are no specific restrictions on values that are too large.

        :param message: given message
        :type message: T
        :return: Matching degree
        :rtype: float
        """
        return 1
    
    @abstractmethod
    def run(self, message: T, /) -> Any:
        raise NotImplementedError
    
    def activate(self) -> None:
        self.dispatchers.add(self)
    
    def deactivate(self) -> None:
        self.dispatchers.discard(self)
    
    @classmethod
    def dispatch(cls, message: T, /, threshold: float = 0.4, filter: Optional[Callable[[Self], bool]] = None) -> Optional[Any]:
        dispatchers = cls.dispatchers
        if filter is not None:
            dispatchers = {d for d in dispatchers if filter(d)}
        if not dispatchers:
            return
        selected, match_rate = max(
            map(lambda d: (d, d.match(message)), dispatchers),
            key=lambda x: x[1],
        )
        if match_rate < threshold:
            return
        elif selected.once:
            selected.deactivate()
        return selected.run(message)
    
    @property
    def activated(self) -> bool:
        return self in self.dispatchers


class FutureDispatcher(AbstractDispatcher[T]):
    __slots__ = ["future"]

    def __init__(self, /, future: asyncio.Future) -> None:
        super().__init__(once=True)
        self.future = future

    def run(self, message: T, /) -> None:
        self.future.set_result(message)
    
    async def wait(self) -> T:
        self.activate()
        return await self.future
