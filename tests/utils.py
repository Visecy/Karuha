import asyncio
import json
from contextlib import asynccontextmanager
from time import time
from types import TracebackType, coroutine
from typing import (AsyncGenerator, Awaitable, Generator, Generic, Optional,
                    Type)
from unittest import IsolatedAsyncioTestCase

from tinode_grpc import pb
from typing_extensions import Self

from karuha.bot import Bot, State
from karuha.config import Server as ServerConfig
from karuha.event import T_Event


TEST_TIME_OUT = 5


@coroutine
def run_forever() -> Generator[None, None, None]:
    while True:
        yield


class BotSimulation(Bot):
    __slots__ = []
    
    def receive_message(self, message: pb.ServerMsg, /) -> None:
        for desc, msg in message.ListFields():
            for e in self.server_event_callbacks[desc.name]:
                e(self, msg)
    
    async def consum_message(self) -> pb.ClientMsg:
        return await self.queue.get()
    
    def clear_message(self) -> None:
        while not self.queue.empty():
            self.queue.get_nowait()
    
    def assert_message_nowait(self, message: pb.ClientMsg, /) -> None:
        assert self.queue.get_nowait() == message
    
    async def assert_message(self, message: pb.ClientMsg, /) -> None:
        assert await self.consum_message() == message

    async def wait_state(self, state: State, /, timeout: float = TEST_TIME_OUT) -> None:
        start = time()
        while self.state != state:
            await asyncio.sleep(0)
            if time() - start > timeout:
                raise TimeoutError(f"bot state has not changed to {state}")

    async def wait_init(self) -> None:
        await self.wait_state(State.running)
    
    def confirm_message(self, tid: Optional[str] = None, code: int = 200, **params: str) -> str:
        if tid is None:
            assert len(self._wait_list) == 1
            tid = list(self._wait_list.keys())[0]
        if code < 200 or code >= 400:
            text = "test error"
        else:
            text = "OK"
        self._wait_list[tid].set_result(
            pb.ServerCtrl(
                id=tid,
                topic="test_topic",
                code=code,
                text=text,
                params={k: json.dumps(v).encode() for k, v in params.items()}
            )
        )
        return tid
    
    async def async_run(self, server_config: Optional[ServerConfig] = None) -> None:
        server = server_config or self.server
        if server is None:
            raise ValueError("server not specified")
        
        self._prepare_loop_task()
        while self.state == State.running:
            self.logger.info(f"starting the bot {self.name}")
            try:
                async with self._run_context() as channel:
                    await channel
            except KeyboardInterrupt:
                break
            except asyncio.CancelledError:
                if self.state == State.restarting:
                    self.state = State.running
                else:
                    raise
    
    @asynccontextmanager
    async def _run_context(self) -> AsyncGenerator[Awaitable, None]:
        try:
            yield run_forever()
        except:  # noqa: E722
            if self.state != State.restarting:
                self.cancel(cancel_loop=False)
            raise
        finally:
            # clean up for restarting
            while not self.queue.empty():
                self.queue.get_nowait()

            for t in self._tasks:
                t.cancel()


bot_simulation = BotSimulation("test", "basic", "123456", log_level="DEBUG")


class EventCatcher(Generic[T_Event]):
    __slots__ = ["event_type", "future", "events"]

    def __init__(self, event_type: Type[T_Event]) -> None:
        self.event_type = event_type
        self.events = []
        self.future = None
    
    def catch_event_nowait(self) -> T_Event:
        return self.events.pop()
    
    async def catch_event(self, timeout: float = TEST_TIME_OUT) -> T_Event:
        if self.events:
            return self.catch_event_nowait()
        assert self.future is None, "catcher is already waiting"
        loop = asyncio.get_running_loop()
        self.future = loop.create_future()
        try:
            return await asyncio.wait_for(self.future, timeout)
        finally:
            self.future = None
    
    @property
    def caught(self) -> bool:
        return bool(self.events)

    async def __call__(self, event: T_Event) -> None:
        if self.future:
            self.future.set_result(event)
        else:
            self.events.append(event)
    
    def __enter__(self) -> Self:
        self.event_type.add_handler(self)
        return self
    
    def __exit__(self, exec_type: Type[BaseException], exec_ins: BaseException, traceback: TracebackType) -> None:
        self.event_type.remove_handler(self)


class AsyncBotTestCase(IsolatedAsyncioTestCase):
    bot = bot_simulation

    async def asyncSetUp(self) -> None:
        self.assertEqual(self.bot.state, State.stopped)
        loop = asyncio.get_running_loop()
        loop.set_debug(True)
        loop.create_task(self.bot.async_run(ServerConfig()))
        await self.bot.wait_init()
    
    async def asyncTearDown(self) -> None:
        self.assertEqual(self.bot.state, State.running)
        self.bot.cancel()
    
    catchEvent = EventCatcher

    async def assertBotMessage(self, message: pb.ClientMsg, /) -> None:
        await self.bot.assert_message(message)
    
    def assertBotMessageNowait(self, message: pb.ClientMsg, /) -> None:
        self.bot.assert_message_nowait(message)
