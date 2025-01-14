from typing import Any, Literal, Optional

from ..bot import Bot, ProxyBot
from ..event.bot import BotFinishEvent, BotReadyEvent
from ..runner import add_bot, run_bot
from ..utils.event_catcher import EventCatcher
from .base import BaseService
from .user import UserService


class BotService(BaseService):
    __slots__ = []

    async def new_bot(
        self,
        uname: str,
        password: str,
        *,
        bot_name: Optional[str] = None,
        use_proxy: bool = False,
        start_run: bool = True,
        ensure_state: bool = True,
        **kwds: Any
    ) -> Bot:
        secret = f"{uname}:{password}"
        user_id, _ = await UserService(self.bot).new_user(uname, password, **kwds)
        if bot_name is None:
            bot_name = f"chatbot_{user_id}"
        if not use_proxy:
            bot = Bot(bot_name, schema="basic", secret=secret, server=self.bot._server_config)
        else:
            bot = ProxyBot.from_bot(self.bot, user_id, bot_name)
        if not start_run:
            return bot
        add_bot(bot)
        if ensure_state:
            with EventCatcher(BotReadyEvent) as catcher:
                ev = await catcher.catch_event()
                while ev.bot is not bot:
                    ev = await catcher.catch_event()
        return bot

    run_bot = staticmethod(run_bot)

    async def attach(
        self,
        schema: Literal["basic", "token", "cookie"],
        secret: str,
        *,
        bot_name: Optional[str] = None,
        start_run: bool = True,
        ensure_state: bool = True,
    ) -> Bot:
        if bot_name is None:
            bot_name = f"chatbot_attach_{self.random_string()}"
        bot = Bot(bot_name, schema=schema, secret=secret, server=self.bot._server_config)
        if not start_run:
            return bot
        add_bot(bot)
        if ensure_state:
            with EventCatcher(BotReadyEvent) as catcher:
                ev = await catcher.catch_event()
                while ev.bot is not bot:
                    ev = await catcher.catch_event()
        return bot
    
    async def attach_in_proxy(
        self,
        user_id: str,
        *,
        bot_name: Optional[str] = None,
        start_run: bool = True,
        ensure_state: bool = True,
    ) -> ProxyBot:
        if bot_name is None:
            bot_name = f"chatbot_proxy_{user_id}"
        bot = ProxyBot.from_bot(self.bot, user_id, bot_name)
        if not start_run:
            return bot
        add_bot(bot)
        if ensure_state:
            with EventCatcher(BotReadyEvent) as catcher:
                ev = await catcher.catch_event()
                while ev.bot is not bot:
                    ev = await catcher.catch_event()
        return bot
    
    async def detach(self, bot: Bot, *, ensure_state: bool = True) -> None:
        bot.cancel()
        if not ensure_state:
            return
        with EventCatcher(BotFinishEvent) as catcher:
            ev = await catcher.catch_event()
            while ev.bot is not bot:
                ev = await catcher.catch_event()
    
    async def del_bot(self, bot: Bot, /, *, hard: bool = False) -> None:
        await self.detach(bot, ensure_state=True)
        await UserService(self.bot).del_user(bot.user_id, hard=hard)
    
    @staticmethod
    def random_string(length: int = 16) -> str:
        import random
        import string

        return "".join(random.choices(string.ascii_letters + string.digits, k=length))
