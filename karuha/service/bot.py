from typing import Any, Literal, Optional, Union, overload
from uuid import uuid4

from ..bot import Bot
from ..config import Bot as BotConfig
from ..event.bot import BotFinishEvent
from ..runner import add_bot, run_bot, _ensure_bot_ready
from ..utils.event_catcher import EventCatcher
from .base import BaseService
from .user import UserService


class BotService(BaseService):
    __slots__ = []

    @overload
    async def new_bot(
        self,
        config: BotConfig,
        /,
        *,
        use_proxy: bool = False,
        run: bool = True,
        ensure_state: bool = True,
        **kwds: Any,
    ) -> Bot: ...

    @overload
    async def new_bot(
        self,
        uname: str,
        password: str,
        /,
        *,
        bot_name: Optional[str] = None,
        use_proxy: bool = False,
        run: bool = True,
        ensure_state: bool = True,
        **kwds: Any,
    ) -> Bot: ...

    async def new_bot(
        self,
        config_or_uname: Union[BotConfig, str],
        /,
        password: Optional[str] = None,
        *,
        bot_name: Optional[str] = None,
        use_proxy: bool = False,
        run: bool = True,
        ensure_state: bool = True,
        **kwds: Any,
    ) -> Bot:
        """Create a new bot instance using either BotConfig or username/password credentials"""
        if isinstance(config_or_uname, BotConfig):
            config = config_or_uname
            if use_proxy:
                user_id, _ = await UserService(self.bot).new_user(config, **kwds)
                bot = self.bot.proxy_to(user_id, bot_name)
            else:
                bot = Bot(config, server=self.bot._server_config)
        else:
            uname = config_or_uname
            if password is None:
                raise ValueError("password is required when creating bot with username")
            secret = f"{uname}:{password}"
            user_id, _ = await UserService(self.bot).new_user(uname, password, **kwds)
            if bot_name is None:
                bot_name = f"chatbot_{user_id}"
            if not use_proxy:
                bot = Bot(bot_name, scheme="basic", secret=secret, server=self.bot._server_config)
            else:
                bot = self.bot.proxy_to(user_id, bot_name)
        if not run:
            return bot
        add_bot(bot)
        if ensure_state:
            await _ensure_bot_ready(bot)
        return bot

    run_bot = staticmethod(run_bot)

    @overload
    async def attach(
        self,
        config: BotConfig,
        /,
        *,
        run: bool = True,
        ensure_state: bool = True,
    ) -> Bot: ...

    @overload
    async def attach(
        self,
        scheme: Literal["basic", "token", "cookie"],
        secret: str,
        /,
        *,
        bot_name: Optional[str] = None,
        run: bool = True,
        ensure_state: bool = True,
    ) -> Bot: ...

    async def attach(
        self,
        scheme_or_config: Union[Literal["basic", "token", "cookie"], BotConfig],
        /,
        secret_or_none: Optional[str] = None,
        *,
        bot_name: Optional[str] = None,
        run: bool = True,
        ensure_state: bool = True,
    ) -> Bot:
        if isinstance(scheme_or_config, BotConfig):
            config = scheme_or_config
            bot = Bot(config, server=self.bot._server_config)
        else:
            scheme = scheme_or_config
            if secret_or_none is None:
                raise ValueError("secret is required when attaching with scheme")
            secret = secret_or_none
            if bot_name is None:
                bot_name = f"chatbot_attach_{uuid4()}"
            bot = Bot(bot_name, scheme=scheme, secret=secret, server=self.bot._server_config)
        if not run:
            return bot
        add_bot(bot)
        if ensure_state:
            await _ensure_bot_ready(bot)
        return bot

    async def attach_in_proxy(
        self,
        user_id: str,
        *,
        bot_name: Optional[str] = None,
        run: bool = True,
        ensure_state: bool = True,
    ) -> Bot:
        if bot_name is None:
            bot_name = f"chatbot_proxy_{user_id}"
        bot = self.bot.proxy_to(user_id, bot_name)
        if not run:
            return bot
        add_bot(bot)
        if ensure_state:
            await _ensure_bot_ready(bot)
        return bot

    async def detach(self, bot: Bot, *, ensure_state: bool = True) -> None:
        bot.cancel()
        if not ensure_state:
            return
        with EventCatcher(BotFinishEvent) as catcher:
            await catcher.catch_event(pred=lambda ev: ev.bot is bot)

    async def del_bot(self, bot: Bot, /, *, hard: bool = False) -> None:
        await self.detach(bot, ensure_state=True)
        await UserService(self.bot).del_user(bot.user_id, hard=hard)
