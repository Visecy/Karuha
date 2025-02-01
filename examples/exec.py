"""
Execute python code or shell commands

NOTE: Executing the commands in this example requires the user to be under staff management.
NOTE: Allowing code execution from a user is a very dangerous behavior and may lead to server compromise.
NOTE: This module is not recommended to be used in production.

Run with:

    python -m karuha ./config.json --module exec

"""

import asyncio
import os
import sys
from io import StringIO
from traceback import format_exc
from typing import List, Optional

from karuha import MessageSession, on_command
from karuha.utils.argparse import ArgumentParser


@on_command("eval")
async def eval_(session: MessageSession, name: str, user_id: str, text: str) -> None:
    user = await session.get_user(user_id, skip_cache=True)
    if not user.staff:
        await session.finish("Permission denied")
    text = text[text.index(name) + len(name) :]
    try:
        result = eval(text, {"session": session})
    except:  # noqa: E722
        await session.send(format_exc())
    else:
        await session.send(f"eavl result: {result}")


@on_command("exec")
async def exec_(session: MessageSession, name: str, user_id: str, text: str) -> None:
    user = await session.get_user(user_id)
    if not user.staff:
        await session.finish("Permission denied")
    text = text[text.index(name) + len(name) :]
    ss = StringIO()
    stdout = sys.stdout
    stderr = sys.stderr
    try:
        sys.stdout = sys.stderr = ss
        exec(text, {"session": session})
    except:  # noqa: E722
        await session.finish(format_exc())
    finally:
        sys.stdout = stdout
        sys.stderr = stderr
    if out := ss.getvalue():
        await session.send(out)


class DateProtocol(asyncio.SubprocessProtocol):
    def __init__(self, exit_future: Optional[asyncio.Future] = None) -> None:
        self.exit_future = exit_future
        self.output = asyncio.Queue()
        self.pipe_closed = False
        self.exited = False

    def pipe_connection_lost(self, fd: int, exc: Optional[Exception]) -> None:
        self.pipe_closed = True
        self.check_for_exit()

    def pipe_data_received(self, fd: int, data: bytes) -> None:
        self.output.put_nowait(data)

    def process_exited(self) -> None:
        self.exited = True
        # process_exited() method can be called before
        # pipe_connection_lost() method: wait until both methods are
        # called.
        self.check_for_exit()

    async def wait(self) -> None:
        if self.pipe_closed and self.exited:
            return
        if self.exit_future is None:
            self.exit_future = asyncio.Future()
        await self.exit_future

    def check_for_exit(self) -> None:
        if self.pipe_closed and self.exited and self.exit_future:
            self.exit_future.set_result(True)
