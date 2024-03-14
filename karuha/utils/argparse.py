import asyncio
from argparse import ArgumentParser as _ArgumentParser
from typing import Any, NoReturn, Optional
from weakref import WeakSet

from ..command import BaseSession


class ArgumentParser(_ArgumentParser):
    __slots__ = ["session", "tasks"]

    def __init__(self, session: BaseSession, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = session
        self.tasks = WeakSet()
    
    def _print_message(self, message: str, file: Any = None) -> None:
        task = asyncio.create_task(self.session.send(message))
        self.tasks.add(task)

    def exit(self, status: int = 0, message: Optional[str] = None) -> NoReturn:
        if message:
            self._print_message(message)
        raise asyncio.CancelledError(status)
    
    async def wait_tasks(self) -> None:
        await asyncio.gather(*self.tasks)
