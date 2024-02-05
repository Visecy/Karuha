import asyncio
import json
from contextlib import asynccontextmanager
from time import time
from types import coroutine
from typing import Any, AsyncGenerator, Awaitable, Dict, Generator, Optional
from unittest import IsolatedAsyncioTestCase

from tinode_grpc import pb

from karuha import async_run, try_add_bot
from karuha.bot import Bot, State
from karuha.config import Server as ServerConfig
from karuha.config import init_config
from karuha.event import T_Event
from karuha.text.message import Message
from karuha.utils.event_catcher import EventCatcher as _EventCatcher


TEST_TIME_OUT = 5


@coroutine
def run_forever() -> Generator[None, None, None]:
    while True:
        yield


class BotMock(Bot):
    __slots__ = []
    
    def receive_message(self, message: pb.ServerMsg, /) -> None:
        for desc, msg in message.ListFields():
            for e in self.server_event_callbacks[desc.name]:
                e(self, msg)
    
    def receive_content(
            self,
            content: bytes,
            *,
            topic: str = "test",
            from_user_id: str = "user",
            seq_id: int = 0,
            head: Dict[str, bytes] = {"auto": b"true"}
    ) -> None:
        self.receive_message(
            pb.ServerMsg(
                data=pb.ServerData(
                    topic=topic,
                    from_user_id=from_user_id,
                    seq_id=seq_id,
                    head=head.copy(),
                    content=content,
                )
            )
        )
    
    async def consum_message(self) -> pb.ClientMsg:
        return await asyncio.wait_for(self.queue.get(), TEST_TIME_OUT)
    
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
    
    def confirm_message(self, tid: Optional[str] = None, code: int = 200, **params: Any) -> str:
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
                topic="test",
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


bot_mock = BotMock("test", "basic", "123456", log_level="DEBUG")


class EventCatcher(_EventCatcher[T_Event]):
    __slots__ = []

    async def catch_event(self, timeout: float = TEST_TIME_OUT) -> T_Event:
        return await super().catch_event(timeout)


class AsyncBotTestCase(IsolatedAsyncioTestCase):
    bot = bot_mock
    config = init_config(log_level="DEBUG")

    async def asyncSetUp(self) -> None:
        self.assertEqual(self.bot.state, State.stopped)
        try_add_bot(self.bot)
        asyncio.create_task(async_run())
        await self.bot.wait_init()
    
    async def asyncTearDown(self) -> None:
        self.assertEqual(self.bot.state, State.running)
        self.bot.cancel()
    
    catchEvent = EventCatcher

    async def assertBotMessage(self, message: pb.ClientMsg, /) -> None:
        await self.bot.assert_message(message)
    
    def assertBotMessageNowait(self, message: pb.ClientMsg, /) -> None:
        self.bot.assert_message_nowait(message)


def new_test_message(content: bytes = b"\"test\"") -> Message:
    return Message.new(
        bot_mock, "test", "user", 1, {}, content
    )
