"""
A simple Tinode chatbot framework
"""

import asyncio
from pathlib import Path


WORKDIR = Path(".bot")  # dir to storage bot data

from .version import __version__
from .config import get_config, load_config, init_config, Config
from .config import Server as ServerConfig, Bot as BotConfig
from .bot import Bot


_bot_cache = {}


def get_bot(name: str = "chatbot") -> Bot:
    config = get_config()
    if name in _bot_cache:
        return _bot_cache[name]
    for i in config.bots:
        if i.name == name:
            bot = Bot(i, server=config.server)
            _bot_cache[name] = bot
            return bot
    raise ValueError(f"bot '{name}' is not in the configuration list")


def run() -> None:
    loop = asyncio.get_event_loop()
    config = get_config()
    for i in config.bots:
        bot = Bot(i, server=config.server)
        loop.create_task(bot.async_run())
    loop.run_forever()


__all__ = [
    "get_config",
    "load_config",
    "init_config",
    "Config",
    "BotConfig",
    "ServerConfig",
    "Bot"
]
