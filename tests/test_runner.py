import asyncio

from karuha.config import get_config
from karuha.runner import (
    DynamicGatheringFuture,
    _get_running_loop,
    add_bot,
    get_all_bots,
    get_bot,
    remove_bot,
    try_add_bot,
    try_get_bot,
)

from .utils import AsyncBotTestCase, BotMock


class TestRunner(AsyncBotTestCase):
    bot1 = BotMock("test1", "basic", "test1:test1")
    bot2 = BotMock("test2", "basic", "test2:test2")

    def test_get_bot(self) -> None:
        self.assertIs(try_get_bot("test"), self.bot)
        self.assertIs(get_bot("test"), self.bot)
        self.assertIsNone(try_get_bot())
        with self.assertRaises((ValueError, KeyError)):
            get_bot()
        self.assertEqual(get_all_bots(), [self.bot])

        config = get_config()
        config.bots += (self.bot1.config,)

        @self.addCleanup
        def _cleanup():
            config.bots = config.bots[:-1]

        bot1 = get_bot("test1")
        self.assertEqual(bot1.name, "test1")
        self.assertIsNot(bot1, self.bot1)
        self.addCleanup(remove_bot, self.bot1)

    def test_add_bot(self) -> None:
        self.assertIsNone(try_get_bot("test1"))
        add_bot(self.bot1)
        self.addCleanup(remove_bot, self.bot1)

        self.assertIs(try_get_bot("test1"), self.bot1)
        self.assertFalse(try_add_bot(self.bot1))
        with self.assertRaises(ValueError):
            add_bot(self.bot1)
        self.assertEqual(get_all_bots(), [self.bot, self.bot1])

    def test_remove_bot(self) -> None:
        with self.assertRaises(ValueError):
            remove_bot(self.bot2)
        add_bot(self.bot2)
        self.assertIs(get_bot("test2"), self.bot2)
        remove_bot(self.bot2)
        self.assertIsNone(try_get_bot("test2"))

    async def test_gathering(self) -> None:
        # test gathering future glabal variable
        _get_running_loop()

        fut = asyncio.Future()
        gathering = DynamicGatheringFuture([fut])
        fut.set_result(1)
        ret = await self.wait_for(gathering)
        self.assertTrue(gathering.done())
        self.assertEqual(ret, [1])

        fut = asyncio.Future()
        fut1 = asyncio.Future()
        gathering = DynamicGatheringFuture([fut, fut1])
        fut.set_result(1)
        fut1.set_exception(ValueError)
        with self.assertRaises(ValueError):
            await self.wait_for(gathering)
