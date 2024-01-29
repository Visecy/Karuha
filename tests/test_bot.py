import asyncio

from tinode_grpc import pb

from karuha.bot import State
from karuha.config import Bot as BotConfig
from karuha.event.bot import (CtrlEvent, DataEvent, InfoEvent, LeaveEvent,
                              LoginEvent, MetaEvent, PresEvent, PublishEvent,
                              SubscribeEvent)

from .utils import TEST_TIME_OUT, AsyncBotTestCase, BotMock


class TestBot(AsyncBotTestCase):
    bot = BotMock("test", "basic", "123456", log_level="DEBUG")

    def test_bot_init(self) -> None:
        self.assertEqual(
            self.bot.config,
            BotConfig(name="test", schema="basic", secret="123456")
        )
        self.assertEqual(
            self.bot.server,
            None
        )
        self.assertTrue(self.bot.queue.empty())
        self.assertFalse(self.bot._tasks)
        self.assertEqual(self.bot.state, State.running)

    async def test_server_message(self) -> None:
        with self.catchEvent(DataEvent) as catcher:
            message = pb.ServerData(
                topic="topic_test",
                content=b"\"Hello world!\"",
                seq_id=114,
                from_user_id="uid_test"
            )
            self.bot.receive_message(pb.ServerMsg(data=message))
            e = await catcher.catch_event()
        self.assertEqual(e.server_message, message)

        with self.catchEvent(CtrlEvent) as catcher:
            message = pb.ServerCtrl(
                id="114",
                topic="topic_test",
            )
            self.bot.receive_message(pb.ServerMsg(ctrl=message))
            e = await catcher.catch_event()
        self.assertEqual(e.server_message, message)

        with self.catchEvent(MetaEvent) as catcher:
            message = pb.ServerMeta(
                id="114",
                topic="topic_test"
            )
            self.bot.receive_message(pb.ServerMsg(meta=message))
            e = await catcher.catch_event()
        self.assertEqual(e.server_message, message)
        
        with self.catchEvent(PresEvent) as catcher:
            message = pb.ServerPres(
                topic="topic_test",
                seq_id=114,
                what=pb.ServerPres.ON
            )
            self.bot.receive_message(pb.ServerMsg(pres=message))
            e = await catcher.catch_event()
        self.assertEqual(e.server_message, message)

        with self.catchEvent(InfoEvent) as catcher:
            message = pb.ServerInfo(
                topic="topic_test",
                from_user_id="uid_test",
                seq_id=114
            )
            self.bot.receive_message(pb.ServerMsg(info=message))
            e = await catcher.catch_event()
        self.assertEqual(e.server_message, message)
    
    async def test_client_message(self) -> None:
        bot = self.bot

        hi_task = asyncio.create_task(bot.hello())
        hi_msg = await bot.consum_message()
        self.assertIsInstance(hi_msg.hi, pb.ClientHi)
        tid = bot.confirm_message(build="tinode-mysql", ver="0.22")
        self.assertEqual(tid, hi_msg.hi.id)
        await asyncio.wait_for(hi_task, TEST_TIME_OUT)

        login_task = asyncio.create_task(bot.login())
        login_msg = await bot.consum_message()
        login_msg_inner = login_msg.login
        self.assertIsInstance(login_msg_inner, pb.ClientLogin)
        self.assertEqual(login_msg_inner.scheme, "basic")
        self.assertEqual(login_msg_inner.secret, b"123456")
        tid = bot.confirm_message(user="user_test", token="token_test")
        self.assertEqual(tid, login_msg_inner.id)
        with self.catchEvent(LoginEvent) as catcher:
            await asyncio.wait_for(login_task, TEST_TIME_OUT)
            e = await catcher.catch_event()
            self.assertEqual(e.client_message, login_msg_inner)
            self.assertIsNotNone(e.response_message)

        sub_msg = await bot.consum_message()
        sub_msg_inner = sub_msg.sub
        self.assertIsInstance(sub_msg_inner, pb.ClientSub)
        self.assertEqual(sub_msg_inner.topic, "me")
        tid = bot.confirm_message()
        self.assertEqual(tid, sub_msg_inner.id)
        with self.catchEvent(SubscribeEvent) as catcher:
            e = await catcher.catch_event()
            self.assertEqual(e.client_message, sub_msg_inner)
            self.assertIsNotNone(e.response_message)
        
        sub_task = asyncio.create_task(bot.subscribe("topic_test"))
        sub_msg = await bot.consum_message()
        sub_msg_inner = sub_msg.sub
        self.assertIsInstance(sub_msg_inner, pb.ClientSub)
        self.assertEqual(sub_msg_inner.topic, "topic_test")
        tid = bot.confirm_message(code=400)
        self.assertEqual(tid, sub_msg_inner.id)
        await asyncio.wait_for(sub_task, TEST_TIME_OUT)
        
        pub_task = asyncio.create_task(bot.publish("topic_test", "Hello world!"))
        pub_msg = await bot.consum_message()
        pub_msg_inner = pub_msg.pub
        self.assertIsInstance(pub_msg_inner, pb.ClientPub)
        self.assertEqual(pub_msg_inner.topic, "topic_test")
        self.assertEqual(pub_msg_inner.content, b"\"Hello world!\"")
        tid = bot.confirm_message()
        self.assertEqual(tid, pub_msg_inner.id)
        with self.catchEvent(PublishEvent) as catcher:
            await asyncio.wait_for(pub_task, TEST_TIME_OUT)
            e = await catcher.catch_event()
            self.assertIsNotNone(e.response_message)
        
        leave_task = asyncio.create_task(bot.leave("topic_test"))
        leave_msg = await bot.consum_message()
        leave_msg_inner = leave_msg.leave
        self.assertIsInstance(leave_msg_inner, pb.ClientLeave)
        self.assertEqual(leave_msg_inner.topic, "topic_test")
        tid = bot.confirm_message()
        self.assertEqual(tid, leave_msg_inner.id)
        with self.catchEvent(LeaveEvent) as catcher:
            await asyncio.wait_for(leave_task, TEST_TIME_OUT)
            e = await catcher.catch_event()
            self.assertIsNotNone(e.response_message)
        
    async def test_restart(self) -> None:
        self.bot.restart()
        self.assertEqual(self.bot.state, State.restarting)
        await self.bot.wait_state(State.running)
