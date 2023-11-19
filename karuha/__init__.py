"""
A simple Tinode chatbot framework
"""

import asyncio
import os
from pathlib import Path
from typing import List
from typing_extensions import deprecated


WORKDIR = Path(os.environ.get("KARUHA_HOME", ".bot"))  # dir to storage bot data


from .version import __version__
from .config import get_config, load_config, init_config, save_config, Config
from .config import Server as ServerConfig, Bot as BotConfig
from .bot import Bot
from .event import *
from .text import Drafty, BaseText, PlainText
from .plugin_server import init_server
from .logger import logger
from .exception import KaruhaException


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


@deprecated("karuha.async_run() is deprecated, using karuha.run() instead")
async def async_run() -> None:
    config = get_config()
    tasks = [asyncio.create_task(bot.async_run()) for bot in _bot_cache.values()]
    for i in config.bots:
        if i.name in _bot_cache:
            bot = _bot_cache[i.name]
        else:
            bot = Bot.from_config(i, config)
        tasks.append(asyncio.create_task(bot.async_run()))
    if not tasks:
        raise ValueError("no bot loaded")
    await asyncio.gather(*tasks)
    

def run() -> None:
    config = get_config()
    loop = asyncio.new_event_loop()

    bots: List[Bot] = []
    for i in config.bots:
        if i.name in _bot_cache:
            bot = _bot_cache[i.name]
        else:
            bot = Bot.from_config(i, config)
            bots.append(bot)
        loop.create_task(bot.async_run())
    
    if config.server.enable_plugin:
        server = init_server(config.server.listen)
        loop.call_soon(server.start)
    else:
        server = None
    
    if config.log_level == "DEBUG":
        loop.set_debug(True)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            for i in bots:
                i.cancel()
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            loop.close()
            if server is not None:
                logger.info("stop plugin server")
                server.stop(None)


__all__ = [
    "get_config",
    "init_config",
    "load_config",
    "save_config",
    "Config",
    "BotConfig",
    "ServerConfig",
    "Bot",
    "on",
    "KaruhaException"
]
