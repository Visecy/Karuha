from io import StringIO

from tinode_grpc import pb
from ..utils import AsyncBotClientTestCase


class TestBotClient(AsyncBotClientTestCase):
    async def test_hi(self) -> None:
        await self.bot.hello()
        await self.bot.hello(lang="CN")

    async def test_upload(self) -> None:
        f = StringIO("Hello world!")
        _, params = await self.bot.upload(f)
        self.assertTrue("url" in params)

        f = StringIO()
        await self.bot.download(params["url"], f)
        self.assertEqual(f.getvalue(), "Hello world!")

    async def test_account(self) -> None:
        _, params = await self.bot.account(
            "newkr_test",
            "basic",
            b"test:test123456",
            cred=[pb.ClientCred(method="email", value="test@example.com")],
            do_login=False,
        )
        uid = params["user"]
        await self.bot.delete("user", user_id=uid, hard=True)
