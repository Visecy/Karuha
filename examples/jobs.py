import asyncio
import os
from io import StringIO
from traceback import format_exc
from typing import List, Optional

from psutil import Process

from karuha import MessageSession, PlainText, on_command
from karuha.text import Italic
from karuha.utils.argparse import ArgumentParser


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


_jobs: List[asyncio.SubprocessTransport] = []


@on_command
async def run(session: MessageSession, name: str, user_id: str, argv: List[str]) -> None:
    user = await session.get_user(user_id)
    if not user.staff:
        await session.finish("Permission denied")
    parser = ArgumentParser(session, name)
    parser.add_argument("-c", "--cwd", help="working directory")
    parser.add_argument("-e", "--env", action="append", help="environment variable")
    # parser.add_argument("-s", "--shell", action="store_true", help="shell mode")
    parser.add_argument("command", nargs="+", help="command to run")
    ns = parser.parse_args(argv)
    if not ns.command:
        await session.finish("No command specified")

    session.bot.logger.info(f"run: {ns.command}")
    loop = asyncio.get_running_loop()
    try:
        transport, protocol = await loop.subprocess_exec(
            DateProtocol,
            *ns.command,
            cwd=ns.cwd,
            env=dict(os.environ, **dict((e.split("=", 1) for e in ns.env or ()))),
            # shell=ns.shell,
            stdin=None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
    except OSError:
        await session.finish(format_exc())

    _jobs.append(transport)
    wait_task = asyncio.create_task(protocol.wait())
    while not wait_task.done():
        done, _ = await asyncio.wait(
            (wait_task, protocol.output.get()),
            return_when=asyncio.FIRST_COMPLETED
        )
        if wait_task in done:
            done.remove(wait_task)
            if not done:
                break
        data: bytes = done.pop().result()  # type: ignore
        if text := data.decode().rstrip():
            await session.send(text)

    while not protocol.output.empty():
        data = protocol.output.get_nowait()
        if text := data.decode().rstrip():
            await session.send(text)

    _jobs.remove(transport)
    code = transport.get_returncode()
    transport.close()
    if code:
        await session.send(
            Italic(
                content=PlainText(f"Process exited with code {code}")
            )
        )


@on_command
async def kill(session: MessageSession, name: str, user_id: str, argv: List[str]) -> None:
    user = await session.get_user(user_id)
    if not user.staff:
        await session.finish("Permission denied")
    parser = ArgumentParser(session, name)
    parser.add_argument("tid", type=int, help="process id", nargs="?")
    parser.add_argument("-s", "--signal", type=int, help="signal to send", default=15)
    ns = parser.parse_args(argv)
    if ns.tid is None:
        # kill all subprocesses
        for transport in _jobs:
            transport.send_signal(ns.signal)
        await session.send("All subprocesses killed")
    else:
        try:
            transport = _jobs[ns.tid]
        except IndexError:
            await session.send("Invalid process id")
        else:
            transport.send_signal(ns.signal)
            await session.send(f"Killed process {ns.tid}")


@on_command
async def jobs(session: MessageSession, name: str, user_id: str, argv: List[str]) -> None:
    user = await session.get_user(user_id)
    if not user.staff:
        await session.finish("Permission denied")
    parser = ArgumentParser(session, name)
    parser.add_argument("-t", "--tid", action="store_true", help="list tid only")
    parser.add_argument("-r", action="store_true", help="restrict output to running jobs")
    parser.add_argument("-s", action="store_true", help="restrict output to stopped jobs")
    ns = parser.parse_args(argv)
    if ns.tid:
        await session.finish('\n'.join(str(i) for i in range(len(_jobs))))
    ss = StringIO()
    for i, transport in enumerate(_jobs):
        pid = transport.get_pid()
        process = Process(pid)
        status = process.status()
        if ns.r and status != "running":
            continue
        if ns.s and status == "running":
            continue
        ss.write(f"[{i}] {status} {' '.join(process.cmdline())}\n")
    if text := ss.getvalue():
        await session.send(text)
