import asyncio
import json
import os
from io import IOBase
import random
import string
from time import time
from typing import (Any, Awaitable, BinaryIO, Callable, ClassVar, Dict,
                    Optional, TypeVar, Union)
from unittest import IsolatedAsyncioTestCase, SkipTest

from tinode_grpc import pb
from aiofiles import open as aio_open

from karuha import (Config, async_run, cancel_all_bots, get_bot, reset,
                    try_add_bot)
from karuha.bot import Bot, BotState
from karuha.command.collection import new_collection
from karuha.command.command import CommandMessage, FunctionCommand
from karuha.config import Server as ServerConfig
from karuha.config import init_config, load_config
from karuha.event.bot import BotReadyEvent
from karuha.server import BaseServer
from karuha.text.message import Message
from karuha.utils.event_catcher import EventCatcher as _EventCatcher
from karuha.utils.event_catcher import T_Event

TEST_TIMEOUT = 3
TEST_UID = "usr_test"
TEST_TOPIC = "grp_test"

T = TypeVar("T")


class MockServer(BaseServer, type="mock"):
    __slots__ = ["send_queue", "recv_queue", "upload_data"]

    async def start(self) -> None:
        if self._running:
            return await super().start()
        self.send_queue = asyncio.Queue()
        self.recv_queue = asyncio.Queue()
        self.upload_data = {}
        return await super().start()
    
    async def put_received(self, message: pb.ServerMsg, /) -> None:
        await self.recv_queue.put(message)
    
    async def get_sent(self) -> pb.ClientMsg:
        return await self.send_queue.get()
    
    async def send(self, msg: pb.ClientMsg) -> None:
        self._ensure_running()
        self.logger.debug(f"out: {msg}")
        await self.send_queue.put(msg)
    
    async def __anext__(self) -> pb.ServerMsg:
        self._ensure_running()
        msg = await self.recv_queue.get()
        self.logger.debug(f"in: {msg}")
        return msg
    
    async def upload(
        self,
        path: Union[str, os.PathLike, BinaryIO],
        auth: str,
        **kwds: Any
    ) -> Dict[str, Any]:
        if isinstance(path, (BinaryIO, IOBase)):
            path.seek(0)
            data = path.read()
        else:
            async with aio_open(path, "rb") as f:
                data = await f.read()
        uri = ''.join(random.choice(string.ascii_letters) for _ in range(32))
        url = f"/v0/file/s/{uri}"
        self.upload_data[url] = data
        return {"url": url}
    
    async def download(
        self,
        url: str,
        path: Union[str, os.PathLike, BinaryIO],
        auth: str,
        *,
        tid: Optional[str] = None
    ) -> int:
        data = self.upload_data[url]
        if isinstance(path, (BinaryIO, IOBase)):
            path.seek(0)
            path.write(data)
        else:
            async with aio_open(path, "wb") as f:
                await f.write(data)
        return len(data)


class BotMock(Bot):
    server: MockServer

    server_info = {}
    account_info = {"user": TEST_UID}

    async def wait_state(self, state: BotState, /, timeout: float = TEST_TIMEOUT) -> None:
        start = time()
        while self.state != state:
            await asyncio.sleep(0)
            if time() - start > timeout:
                raise TimeoutError(f"bot state has not changed to {state}")

    async def wait_init(self) -> None:
        with EventCatcher(BotReadyEvent) as catcher:
            await catcher.catch_event(pred=lambda ev: ev.bot is self)
    
    async def _prepare_account(self) -> None:
        self.server_info = {}
        self.account_info = {"user": TEST_UID}
    

bot_mock_server = ServerConfig(connect_mode="mock")
bot_mock = BotMock("test", "basic", "123456", log_level="DEBUG")


class EventCatcher(_EventCatcher[T_Event]):
    __slots__ = []

    async def catch_event(
        self,
        timeout: Optional[float] = TEST_TIMEOUT,
        *,
        pred: Callable[[T_Event], bool] = lambda _: True,
    ) -> T_Event:
        return await super().catch_event(timeout, pred=pred)


class AsyncBotTestCase(IsolatedAsyncioTestCase):
    bot = bot_mock
    config: ClassVar[Config]

    @classmethod
    def setUpClass(cls) -> None:
        reset()
        cls.config = init_config(log_level="DEBUG", server=bot_mock_server)

    async def asyncSetUp(self) -> None:
        self.assertEqual(self.bot.state, BotState.stopped)
        try_add_bot(self.bot)
        self._main_task = asyncio.create_task(async_run())
        await self.bot.wait_init()
    
    async def asyncTearDown(self) -> None:
        self.assertEqual(self.bot.state, BotState.running)
        cancel_all_bots()
        try:
            await self.wait_for(self._main_task)
        except asyncio.CancelledError:
            pass
    
    catchEvent = EventCatcher

    async def get_bot_sent(self) -> pb.ClientMsg:
        return await self.wait_for(self.bot.server.get_sent())
    
    async def put_bot_received(self, message: pb.ServerMsg, /) -> None:
        await self.bot.server.put_received(message)
    
    def get_latest_tid(self) -> str:
        assert len(self.bot._wait_list) == 1
        return tuple(self.bot._wait_list.keys())[0]
    
    def confirm_message(self, tid: Optional[str] = None, code: int = 200, **params: Any) -> str:
        if tid is None:
            tid = self.get_latest_tid()
        text = "test error" if code < 200 or code >= 400 else "OK"
        self.bot._wait_list[tid].set_result(
            pb.ServerCtrl(
                id=tid,
                code=code,
                text=text,
                params={k: json.dumps(v).encode() for k, v in params.items()}
            )
        )
        return tid
    
    async def assert_bot_message(self, message: pb.ClientMsg, /) -> None:
        sent = await self.get_bot_sent()
        self.assertEqual(sent, message)
    
    async def get_bot_pub(self, seq: int = 0) -> pb.ClientPub:
        msg = await self.get_bot_sent()
        if msg.HasField("note"):
            # from DataEvent handler
            msg = await self.get_bot_sent()
        if msg.HasField("sub"):
            # from session.send
            self.confirm_message(msg.sub.id)
            msg = await self.get_bot_sent()
        self.assertTrue(msg.HasField("pub"), f"{msg} is not pub")
        self.confirm_message(msg.pub.id, seq=seq)
        return msg.pub
    
    async def put_bot_content(
            self,
            content: bytes,
            *,
            topic: str = TEST_TOPIC,
            from_user_id: str = TEST_UID,
            seq_id: int = 0,
            head: Dict[str, bytes] = {"auto": b"true"}
    ) -> None:
        await self.put_bot_received(
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
    
    async def assert_bot_sub(self, topic: Optional[str] = None) -> None:
        msg = await self.get_bot_sent()
        self.assertTrue(msg.HasField("sub"), f"{msg} is not sub")
        if topic is not None:
            self.assertEqual(msg.sub.topic, topic)
        self.confirm_message(msg.sub.id)
    
    async def assert_bot_leave(self, topic: Optional[str] = None) -> None:
        msg = await self.get_bot_sent()
        self.assertTrue(msg.HasField("leave"), f"{msg} is not leave")
        if topic is not None:
            self.assertEqual(msg.leave.topic, topic)
        self.confirm_message(msg.leave.id)
    
    async def assert_note_read(self, topic: str, seq_id: int, /) -> None:
        assert await self.get_bot_sent() == pb.ClientMsg(
            note_read=pb.ClientNote(topic=topic, seq_id=seq_id, what=pb.READ)
        )
    
    async def wait_for(self, future: Awaitable[T], /, timeout: Optional[float] = TEST_TIMEOUT) -> T:
        return await asyncio.wait_for(future, timeout)


class AsyncBotOnlineTestCase(IsolatedAsyncioTestCase):
    config_path = "config.json"
    bot_name = "chatbot"
    auto_login: ClassVar[bool] = True
    bot: ClassVar[Bot]

    __unittest_skip__ = False
    __unittest_skip_why__ = None

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.config = load_config(cls.config_path, auto_create=False)
            cls.bot = get_bot(cls.bot_name)
        except Exception:
            cls.__unittest_skip__ = True
            cls.__unittest_skip_why__ = "not bot config found"
            raise SkipTest(cls.__unittest_skip_why__) from None
        cls.bot.config.auto_login = cls.auto_login
    
    async def asyncSetUp(self) -> None:
        self.assertEqual(self.bot.state, BotState.stopped)
        try_add_bot(self.bot)
        self._main_task = asyncio.create_task(async_run())
        with EventCatcher(BotReadyEvent) as catcher:
            await catcher.catch_event(pred=lambda ev: ev.bot is self.bot)
    
    async def asyncTearDown(self) -> None:
        self.assertEqual(self.bot.state, BotState.running)
        cancel_all_bots()
        try:
            await self.wait_for(self._main_task)
        except asyncio.CancelledError:
            pass
    
    catchEvent = EventCatcher

    async def wait_for(self, future: Awaitable[T], /, timeout: Optional[float] = TEST_TIMEOUT) -> T:
        return await asyncio.wait_for(future, timeout)
    

def new_test_message(content: bytes = b"\"test\"", *, topic: str = TEST_TOPIC, user_id: str = TEST_UID) -> Message:
    return Message.new(
        bot_mock, topic, user_id, 1, {}, content
    )


def new_test_command_message(content: bytes = b"\"test\"") -> CommandMessage:
    return CommandMessage.from_message(
        new_test_message(content),
        FunctionCommand("test", lambda: None),
        new_collection(),
        "test",
        []
    )
