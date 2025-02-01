from contextlib import AbstractAsyncContextManager, AbstractContextManager
from types import TracebackType
from typing import Any, Generic, Type, TypeVar

from typing_extensions import Self

T = TypeVar("T")


class _ContextHelper(AbstractContextManager):
    __slots__ = []

    def __enter__(self) -> Self:
        self.activate()
        return self

    def __exit__(self, exc_type: Type[BaseException], exc_ins: BaseException, traceback: TracebackType) -> None:
        self.deactivate()

    def activate(self) -> None:
        raise NotImplementedError

    def deactivate(self) -> None:
        raise NotImplementedError


class nullcontext(AbstractContextManager, AbstractAsyncContextManager, Generic[T]):
    """Context manager that does no additional processing.

    Used as a stand-in for a normal context manager, when a particular
    block of code is only sometimes used with a normal context manager:

    cm = optional_cm if condition else nullcontext()
    with cm:
        # Perform operation, using optional_cm if condition is True
    """

    def __init__(self, enter_result: T = None) -> None:
        self.enter_result = enter_result

    def __enter__(self) -> T:
        return self.enter_result

    def __exit__(self, *excinfo: Any) -> None:
        pass

    async def __aenter__(self) -> T:
        return self.enter_result

    async def __aexit__(self, *excinfo: Any) -> None:
        pass
