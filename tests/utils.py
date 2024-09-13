import asyncio
import json
from time import time
from types import coroutine
from typing import Any, Awaitable, Dict, Generator, Optional
from unittest import IsolatedAsyncioTestCase

from grpc import ChannelConnectivity
from grpc import aio as grpc_aio
from tinode_grpc import pb
from typing_extensions import Self

from karuha import async_run, try_add_bot
from karuha.bot import Bot, BotState
from karuha.command.collection import new_collection
from karuha.command.command import CommandMessage, FunctionCommand
from karuha.config import Server as ServerConfig
from karuha.config import init_config
from karuha.store import T
from karuha.text.message import Message
from karuha.utils.event_catcher import T_Event
from karuha.utils.event_catcher import EventCatcher as _EventCatcher


TEST_TIMEOUT = 3


@coroutine
def run_forever() -> Generator[None, None, None]:
    while True:
        yield


class NoopChannel(grpc_aio.Channel):
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        pass

    async def close(self, grace: Optional[float] = None) -> None:
        return
    
    async def get_state(self, try_to_connect: bool = False) -> ChannelConnectivity:
        raise NotImplementedError
    
    async def wait_for_state_change(self, last_observed_state: ChannelConnectivity) -> None:
        raise NotImplementedError
    
    async def channel_ready(self) -> None:
        return
    
    def unary_unary(
        self,
        method: str,
        request_serializer: Optional[grpc_aio._typing.SerializingFunction] = None,
        response_deserializer: Optional[grpc_aio._typing.DeserializingFunction] = None
    ) -> grpc_aio.UnaryUnaryMultiCallable:
        raise NotImplementedError
    
    def unary_stream(
        self,
        method: str,
        request_serializer: Optional[grpc_aio._typing.SerializingFunction] = None,
        response_deserializer: Optional[grpc_aio._typing.DeserializingFunction] = None
    ) -> grpc_aio.UnaryStreamMultiCallable:
        raise NotImplementedError
    
    def stream_unary(
        self,
        method: str,
        request_serializer: Optional[grpc_aio._typing.SerializingFunction] = None,
        response_deserializer: Optional[grpc_aio._typing.DeserializingFunction] = None
    ) -> grpc_aio.StreamUnaryMultiCallable:
        raise NotImplementedError
    
    def stream_stream(
        self,
        method: str,
        request_serializer: Optional[grpc_aio._typing.SerializingFunction] = None,
        response_deserializer: Optional[grpc_aio._typing.DeserializingFunction] = None
    ) -> grpc_aio.StreamStreamMultiCallable:
        raise NotImplementedError


class BotMock(Bot):
    user_id = "usr"
    
    def receive_message(self, message: pb.ServerMsg, /) -> None:
        self.logger.debug(f"in: {message}")
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
        return await asyncio.wait_for(self.queue.get(), TEST_TIMEOUT)
    
    def clear_message(self) -> None:
        while not self.queue.empty():
            self.queue.get_nowait()
    
    def assert_message_nowait(self, message: pb.ClientMsg, /) -> None:
        assert self.queue.get_nowait() == message
    
    async def assert_message(self, message: pb.ClientMsg, /) -> None:
        assert await self.consum_message() == message
    
    async def assert_note_read(self, topic: str, seq_id: int, /) -> None:
        assert await self.consum_message() == pb.ClientMsg(
            note_read=pb.ClientNote(topic=topic, seq_id=seq_id, what=pb.READ)
        )

    async def wait_state(self, state: BotState, /, timeout: float = TEST_TIMEOUT) -> None:
        start = time()
        while self.state != state:
            await asyncio.sleep(0)
            if time() - start > timeout:
                raise TimeoutError(f"bot state has not changed to {state}")

    async def wait_init(self) -> None:
        await self.wait_state(BotState.running)
        hi_msg = await self.consum_message()
        assert hi_msg.hi
        self.confirm_message(hi_msg.hi.id, ver="0.22", build="mysql:v0.22.11")
        login_msg = await self.consum_message()
        assert login_msg.login
        self.confirm_message(login_msg.login.id, user="usr")
        sub_msg = await self.consum_message()
        assert sub_msg.sub and sub_msg.sub.topic == "me"
        self.confirm_message(sub_msg.sub.id)
    
    def get_latest_tid(self) -> str:
        assert len(self._wait_list) == 1
        return tuple(self._wait_list.keys())[0]
    
    def confirm_message(self, tid: Optional[str] = None, code: int = 200, **params: Any) -> str:
        if tid is None:
            tid = self.get_latest_tid()
        text = "test error" if code < 200 or code >= 400 else "OK"
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
        while self.state == BotState.running:
            self.logger.info(f"starting the bot {self.name}")
            async with self._run_context(server):
                await run_forever()
    
    def _get_channel(self, server_config: ServerConfig) -> grpc_aio.Channel:
        return NoopChannel()


bot_mock = BotMock("test", "basic", "123456", log_level="DEBUG")


class EventCatcher(_EventCatcher[T_Event]):
    __slots__ = []

    async def catch_event(self, timeout: float = TEST_TIMEOUT) -> T_Event:
        return await super().catch_event(timeout)


class AsyncBotTestCase(IsolatedAsyncioTestCase):
    bot = bot_mock
    config = init_config(log_level="DEBUG")

    async def asyncSetUp(self) -> None:
        self.assertEqual(self.bot.state, BotState.stopped)
        try_add_bot(self.bot)
        self._main_task = asyncio.create_task(async_run())
        await self.bot.wait_init()
    
    async def asyncTearDown(self) -> None:
        self.assertEqual(self.bot.state, BotState.running)
        self.bot.cancel()
    
    catchEvent = EventCatcher

    async def assertBotMessage(self, message: pb.ClientMsg, /) -> None:
        await self.bot.assert_message(message)
    
    def assertBotMessageNowait(self, message: pb.ClientMsg, /) -> None:
        self.bot.assert_message_nowait(message)
    
    async def get_bot_pub(self) -> pb.ClientPub:
        msg = await self.bot.consum_message()
        if msg.HasField("sub"):
            self.bot.confirm_message(msg.sub.id)
            msg = await self.bot.consum_message()
        self.assertTrue(msg.HasField("pub"))
        return msg.pub
    
    async def reply_bot_sub(self) -> None:
        msg = await self.bot.consum_message()
        assert msg.HasField("sub"), f"{msg} is not sub"
        self.bot.confirm_message(msg.sub.id)
    
    async def reply_bot_leave(self) -> None:
        msg = await self.bot.consum_message()
        assert msg.HasField("leave"), f"{msg} is not leave"
        self.bot.confirm_message(msg.leave.id)
    
    async def wait_for(self, future: Awaitable[T], /, timeout: Optional[float] = TEST_TIMEOUT) -> T:
        return await asyncio.wait_for(future, timeout)


def new_test_message(content: bytes = b"\"test\"") -> Message:
    return Message.new(
        bot_mock, "test", "user", 1, {}, content
    )


def new_test_command_message(content: bytes = b"\"test\"") -> CommandMessage:
    return CommandMessage.from_message(
        new_test_message(content),
        FunctionCommand("test", lambda: None),
        new_collection(),
        "test",
        []
    )
