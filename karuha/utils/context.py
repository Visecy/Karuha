from types import TracebackType
from typing import Type
from typing_extensions import Self


class _ContextHelper(object):
    __slots__ = []

    def __enter__(self) -> Self:
        self.activate()  # type: ignore
        return self
    
    def __exit__(self, exc_type: Type[BaseException], exc_ins: BaseException, traceback: TracebackType) -> None:
        self.deactivate()  # type: ignore
