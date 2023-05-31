"""
A simple Tinode chatbot framework
"""

import asyncio
from pathlib import Path


WORKDIR = Path(".bot")  # dir to storage bot data

from .version import __version__
from .config import get_config, load_config, init_config, save_config, Config
from .config import Server as ServerConfig, Bot as BotConfig
from .bot import Bot
from .exception import KaruhaException, KaruhaConnectError


_bot_cache = {}


def get_bot(name: str = "chatbot") -> Bot:
    config = get_config()
    if name in _bot_cache:
        return _bot_cache[name]
    bot = Bot.from_config(name, config)
    _bot_cache[name] = bot
    return bot


def add_bot(bot: Bot) -> None:
    if bot.name in _bot_cache:
        raise ValueError(f"bot {bot.name} has existed")
    _bot_cache[bot.name] = bot


def run() -> None:
    loop = asyncio.new_event_loop()
    config = get_config()
    for bot in _bot_cache.values():
        loop.create_task(bot.async_run())
    for i in config.bots:
        if i.name in _bot_cache:
            continue
        bot = Bot.from_config(i, config)
        loop.create_task(bot.async_run())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    except asyncio.CancelledError:
        raise KaruhaConnectError("the connection was closed by remote") from None
    finally:
        asyncio.runners._cancel_all_tasks(loop)  # type: ignore
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())
        finally:
            loop.close()


__all__ = [
    "get_config",
    "init_config",
    "load_config",
    "save_config",
    "Config",
    "BotConfig",
    "ServerConfig",
    "Bot",
    "KaruhaException"
]
