from karuha.service import UserService
from ..utils import AsyncBotOnlineTestCase


class TestService(AsyncBotOnlineTestCase):
    async def test_new_user(self) -> None:
        svc = UserService(self.bot)
        uid, _ = await svc.new_user("test", "test123", fn="Test")
        try:
            self.assertRegex(uid, r"^usr.+$")
            self.assertEqual(await svc.get_fn(uid), "Test")
        finally:
            await svc.del_user(uid, hard=True)

    async def test_set_desc(self) -> None:
        svc = UserService(self.bot)
        uid, _ = await svc.new_user("test", "test123", fn="Test")
        try:
            await svc.set_fn(uid, "Test2")
            self.assertEqual(await svc.get_fn(uid), "Test2")
            await svc.set_trusted(uid, {"staff": True})
            self.assertTrue(await svc.is_staff(uid))
            await self.bot.subscribe(uid)
            await svc.set_comment(uid, "Test User")
            self.assertEqual(await svc.get_comment(uid, skip_cache=True), "Test User")
        finally:
            await svc.del_user(uid, hard=True)

    async def test_set_me_desc(self) -> None:
        svc = UserService(self.bot)
        user = await svc.get_user("me")
        user1 = await svc.get_user(self.bot.user_id)
        self.assertEqual(user.user_id, user1.user_id)
        self.assertEqual(user.public, user1.public)

        self.assertEqual(await svc.get_public(self.bot.uid), await svc.get_public("me"))
        is_staff = await svc.is_staff("me")
        await svc.set_trusted("me", {"staff": not is_staff}, update=True)
        self.assertEqual(await svc.is_staff("me", skip_cache=True), not is_staff)
        await svc.set_trusted("me", {"staff": is_staff}, update=True)
        self.assertEqual(await svc.is_staff("me", skip_cache=True), is_staff)
