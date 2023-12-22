import asyncio
from unittest import skip
from tinode_grpc import pb

from karuha.config import Bot as BotConfig
from karuha.event.bot import CtrlEvent, DataEvent, InfoEvent, MetaEvent, PresEvent

from .utils import AsyncBotTestCase, BotSimulation


class TestBot(AsyncBotTestCase):
    bot = BotSimulation("test", "basic", "123456", log_level="DEBUG")

    def test_init(self) -> None:
        print("ts")
        self.assertEqual(
            self.bot.config,
            BotConfig(name="test", schema="basic", secret="123456")
        )
        self.assertEqual(
            self.bot.server,
            None
        )
        self.assertTrue(self.bot.queue.empty())

    async def test_server_message(self) -> None:
        print("ts")
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
