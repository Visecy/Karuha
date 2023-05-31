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


async def async_run() -> None:
    config = get_config()
    tasks = [asyncio.create_task(bot.async_run()) for bot in _bot_cache.values()]
    for i in config.bots:
        if i.name in _bot_cache:
            continue
        bot = Bot.from_config(i, config)
        tasks.append(asyncio.create_task(bot.async_run()))
    await asyncio.gather(*tasks)
    

def run() -> None:
    try:
        asyncio.run(async_run())
    except KeyboardInterrupt:
        pass
    except asyncio.CancelledError:
        raise KaruhaConnectError("the connection was closed by remote") from None


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
