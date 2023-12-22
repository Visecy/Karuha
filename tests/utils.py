import asyncio
from contextlib import asynccontextmanager
from traceback import print_exc
from types import TracebackType
from typing import AsyncGenerator, Coroutine, Generic, Optional, Type
from unittest import IsolatedAsyncioTestCase
from weakref import ref

from tinode_grpc import pb
from typing_extensions import Self

from karuha.bot import Bot, State
from karuha.config import Server as ServerConfig
from karuha.event import T_Event
from karuha.exception import KaruhaBotError


class BotSimulation(Bot):
    __slots__ = []
    
    def receive_message(self, message: pb.ServerMsg, /) -> None:
        for desc, msg in message.ListFields():
            for e in self.server_event_map[desc.name]:
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

    async def wait_init(self) -> None:
        await self.assert_message(pb.ClientMsg(hi=pb.ClientHi()))

    async def async_run(self, server_config: Optional[ServerConfig] = None) -> None:
        server = server_config or self.server
        if server is None:
            raise ValueError("server not specified")
        try:
            async with self._run_context() as future:
                await self._send_message(hi=pb.ClientHi())
                await future
        except KeyboardInterrupt:
            pass
    
    @asynccontextmanager
    async def _run_context(self) -> AsyncGenerator[Coroutine, None]:
        if self.state == State.running:
            raise KaruhaBotError(f"rerun bot {self.name}")
        elif self.state != State.stopped:
            raise KaruhaBotError(f"fail to run bot {self.name} (state: {self.state})")
        self.state = State.running

        self._loop_task_ref = ref(asyncio.current_task())
        self.logger.info(f"starting the bot {self.name}")
        try:
            # Here a better way is to create a future like:
            #   yield asyncio.get_running_loop().create_future()
            # But doing this will cause a GeneratorExit exception
            # that is difficult for me to understand when async_run is running,
            # so I finally adopted the following solution.
            yield asyncio.sleep(100)
        except:  # noqa: E722
            print_exc()
            self.cancel(cancel_loop=False)
            raise


bot_simulation = BotSimulation("test", "basic", "123456", log_level="DEBUG")


class EventCatcher(Generic[T_Event]):
    __slots__ = ["event_type", "future", "events"]

    def __init__(self, event_type: Type[T_Event]) -> None:
        self.event_type = event_type
        self.events = []
        self.future = None
    
    def catch_event_nowait(self) -> T_Event:
        return self.events.pop()
    
    async def catch_event(self, timeout: float = 5) -> T_Event:
        if self.events:
            return self.catch_event_nowait()
        assert self.future is None
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
        # self.bot = BotSimulation("test", "basic", "123456", log_level="DEBUG")
        assert self.bot.state == State.stopped
        self.bot.queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        loop.set_debug(True)
        loop.create_task(self.bot.async_run(ServerConfig()))
        await self.bot.wait_init()
        print("sf")
    
    async def asyncTearDown(self) -> None:
        assert self.bot.state == State.running
        self.bot.cancel()
    
    catchEvent = EventCatcher
