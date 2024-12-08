from io import BytesIO

from tinode_grpc import pb

from karuha import BaseSession, MessageSession, on_rule
from karuha.bot import ProxyBot
from karuha.runner import run_bot
from ..utils import AsyncBotClientTestCase


class TestBotClient(AsyncBotClientTestCase):
    async def test_hi(self) -> None:
        await self.bot.hello()
        await self.bot.hello(lang="CN")

    async def test_upload(self) -> None:
        f = BytesIO(b"Hello world!")
        _, params = await self.bot.upload(f)
        self.assertTrue("url" in params)

        f = BytesIO()
        await self.bot.download(params["url"], f)
        self.assertEqual(f.getvalue(), b"Hello world!")

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
    
    async def test_anonymous_account(self) -> None:
        _, params = await self.bot.account(
            "newkr_anon_test",
            "anonymous",
            do_login=False,
        )
        uid = params["user"]
        await self.bot.delete("user", user_id=uid)
    
    async def test_proxy_bot(self) -> None:
        _, params = await self.bot.account(
            "new",
            "basic",
            b"test:test123456",
            state="ok",
            cred=[pb.ClientCred(method="email", value="test@example.com")],
            do_login=False,
        )
        uid = params["user"]
        try:
            async with run_bot(ProxyBot.from_bot(self.bot, on_behalf_of=uid)) as agent_bot:
                assert isinstance(agent_bot, ProxyBot)
                self.assertEqual(agent_bot.user_id, uid)
                self.assertEqual(agent_bot.login_user_id, self.bot.user_id)

                @on_rule(user_id=uid, bot=self.bot, once=True)
                async def _handler(session: MessageSession, text: str) -> None:
                    self.assertEqual(text, "test")
                    await session.send("test_reply")
                
                async with BaseSession(agent_bot, self.bot.user_id) as session:
                    await session.send("test")
                    reply = await session.wait_reply()
                    self.assertEqual(reply.plain_text, "test_reply")
        finally:
            await self.bot.delete("user", user_id=uid, hard=True)
