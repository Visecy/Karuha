from karuha.service import TopicService
from ..utils import AsyncBotOnlineTestCase


class TestTopicService(AsyncBotOnlineTestCase):
    async def test_new_topic(self) -> None:
        svc = TopicService(self.bot)
        topic_id = await svc.new_topic(fn="Test Group")

        try:
            self.assertEqual(await svc.get_fn(topic_id), "Test Group")
        finally:
            await svc.del_topic(topic_id, hard=True)

        topic_id = await svc.new_topic(fn="Test Channel", is_chan=True)
        try:
            self.assertEqual(await svc.get_fn(topic_id), "Test Channel")
        finally:
            await svc.del_topic(topic_id, hard=True)

    async def test_set_desc(self) -> None:
        svc = TopicService(self.bot)
        topic_id = await svc.new_topic(fn="Test")
        try:
            topic = await svc.get_topic(topic_id)
            self.assertEqual(topic.fn, "Test")
            await svc.set_fn(topic_id, "Test2")
            self.assertEqual(await svc.get_fn(topic_id, skip_cache=True), "Test2")
            await self.bot.subscribe(topic_id)
            await svc.set_trusted(topic_id, {"staff": True})
            self.assertTrue(await svc.is_staff(topic_id, skip_cache=True))
            await svc.set_comment(topic_id, "Test")
            self.assertEqual(await svc.get_comment(topic_id, skip_cache=True), "Test")
        finally:
            await svc.del_topic(topic_id, hard=True)
