import asyncio

from tinode_grpc import pb

from karuha.bot import BotState
from karuha.config import Bot as BotConfig
from karuha.event.bot import (CtrlEvent, DataEvent, InfoEvent, LeaveEvent,
                              LoginEvent, MetaEvent, PresEvent, PublishEvent,
                              SubscribeEvent)
from karuha.exception import KaruhaBotError
from karuha.runner import remove_bot

from .utils import TEST_TIMEOUT, AsyncBotTestCase, BotMock, MockServer, bot_mock_server


class TestBot(AsyncBotTestCase):
    bot = BotMock("test_bot", "basic", "123456", log_level="DEBUG")

    def test_bot_init(self) -> None:
        self.assertEqual(
            self.bot.config,
            BotConfig(name="test_bot", scheme="basic", secret="123456")
        )
        self.assertEqual(
            self.bot.server_config,
            bot_mock_server
        )
        self.assertIsInstance(self.bot.server, MockServer)
        self.assertEqual(self.bot.state, BotState.running)

    async def test_server_message(self) -> None:
        with self.catchEvent(DataEvent) as catcher:
            message = pb.ServerData(
                topic="topic_test",
                content=b"\"Hello world!\"",
                seq_id=114,
                from_user_id="uid_test"
            )
            await self.put_bot_received(pb.ServerMsg(data=message))
            e = await catcher.catch_event()
        self.assertEqual(e.server_message, message)

        with self.catchEvent(CtrlEvent) as catcher:
            message = pb.ServerCtrl(
                id="114",
                topic="topic_test",
            )
            await self.put_bot_received(pb.ServerMsg(ctrl=message))
            e = await catcher.catch_event()
        self.assertEqual(e.server_message, message)

        with self.catchEvent(MetaEvent) as catcher:
            message = pb.ServerMeta(
                id="114",
                topic="topic_test"
            )
            await self.put_bot_received(pb.ServerMsg(meta=message))
            e = await catcher.catch_event()
        self.assertEqual(e.server_message, message)
        
        with self.catchEvent(PresEvent) as catcher:
            message = pb.ServerPres(
                topic="topic_test",
                seq_id=114,
                what=pb.ServerPres.ON
            )
            await self.put_bot_received(pb.ServerMsg(pres=message))
            e = await catcher.catch_event()
        self.assertEqual(e.server_message, message)

        with self.catchEvent(InfoEvent) as catcher:
            message = pb.ServerInfo(
                topic="topic_test",
                from_user_id="uid_test",
                seq_id=114
            )
            await self.put_bot_received(pb.ServerMsg(info=message))
            e = await catcher.catch_event()
        self.assertEqual(e.server_message, message)
    
    async def test_client_message(self) -> None:
        bot = self.bot

        hi_task = asyncio.create_task(bot.hello())
        hi_msg = await self.get_bot_sent()
        self.assertIsInstance(hi_msg.hi, pb.ClientHi)
        tid = self.confirm_message(build="tinode-mock", ver="0.22")
        self.assertEqual(tid, hi_msg.hi.id)
        await asyncio.wait_for(hi_task, TEST_TIMEOUT)

        login_task = asyncio.create_task(bot.login())
        login_msg = await self.get_bot_sent()
        login_msg_inner = login_msg.login
        self.assertIsInstance(login_msg_inner, pb.ClientLogin)
        self.assertEqual(login_msg_inner.scheme, "basic")
        self.assertEqual(login_msg_inner.secret, b"123456")
        tid = self.confirm_message(user="user_test", token="token_test", expires=1708360886000)
        self.assertEqual(tid, login_msg_inner.id)
        with self.catchEvent(LoginEvent) as catcher:
            await asyncio.wait_for(login_task, TEST_TIMEOUT)
            e = await catcher.catch_event()
            self.assertEqual(e.client_message, login_msg_inner)
            self.assertIsNotNone(e.response_message)

        sub_task = asyncio.create_task(bot.subscribe("me"))
        sub_msg = await self.get_bot_sent()
        sub_msg_inner = sub_msg.sub
        self.assertIsInstance(sub_msg_inner, pb.ClientSub)
        self.assertEqual(sub_msg_inner.topic, "me")
        tid = self.confirm_message()
        self.assertEqual(tid, sub_msg_inner.id)
        with self.catchEvent(SubscribeEvent) as catcher:
            e = await catcher.catch_event()
            self.assertEqual(e.client_message, sub_msg_inner)
            self.assertIsNotNone(e.response_message)
        
        sub_task = asyncio.create_task(bot.subscribe("topic_test"))
        sub_msg = await self.get_bot_sent()
        sub_msg_inner = sub_msg.sub
        self.assertIsInstance(sub_msg_inner, pb.ClientSub)
        self.assertEqual(sub_msg_inner.topic, "topic_test")
        tid = self.confirm_message(code=400)
        self.assertEqual(tid, sub_msg_inner.id)
        with self.assertRaises(KaruhaBotError):
            await asyncio.wait_for(sub_task, TEST_TIMEOUT)
        
        pub_task = asyncio.create_task(bot.publish("topic_test", "Hello world!"))
        pub_msg = await self.get_bot_sent()
        pub_msg_inner = pub_msg.pub
        self.assertIsInstance(pub_msg_inner, pb.ClientPub)
        self.assertEqual(pub_msg_inner.topic, "topic_test")
        self.assertEqual(pub_msg_inner.content, b"\"Hello world!\"")
        tid = self.confirm_message(seq=114)
        self.assertEqual(tid, pub_msg_inner.id)
        with self.catchEvent(PublishEvent) as catcher:
            await self.wait_for(pub_task)
            e = await catcher.catch_event()
            self.assertIsNotNone(e.response_message)
            self.assertEqual(e.seq_id, 114)
        
        leave_task = asyncio.create_task(bot.leave("topic_test"))
        leave_msg = await self.get_bot_sent()
        leave_msg_inner = leave_msg.leave
        self.assertIsInstance(leave_msg_inner, pb.ClientLeave)
        self.assertEqual(leave_msg_inner.topic, "topic_test")
        tid = self.confirm_message()
        self.assertEqual(tid, leave_msg_inner.id)
        with self.catchEvent(LeaveEvent) as catcher:
            await asyncio.wait_for(leave_task, TEST_TIMEOUT)
            e = await catcher.catch_event()
            self.assertIsNotNone(e.response_message)
        
    async def test_restart(self) -> None:
        self.bot.restart()
        self.assertEqual(self.bot.state, BotState.restarting)
        await self.bot.wait_state(BotState.running)
    
    @classmethod
    def tearDownClass(cls) -> None:
        remove_bot(cls.bot)
