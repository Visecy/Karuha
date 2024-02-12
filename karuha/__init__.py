"""
A simple Tinode chatbot framework
"""

import asyncio
import os
from pathlib import Path
from typing import Dict, List


WORKDIR = Path(os.environ.get("KARUHA_HOME", ".bot"))  # dir to storage bot data


from .version import __version__
from .config import get_config, load_config, init_config, save_config, Config
from .config import Server as ServerConfig, Bot as BotConfig
from .bot import Bot
from .event import on, on_event, Event
from .exception import KaruhaException
from .command import CommandCollection, AbstractCommand, AbstractCommandParser, BaseSession, MessageSession, get_collection, on_command
from .event.message import reset_message_lock
from .text import Drafty, BaseText, PlainText, Message, TextChain
from .logger import logger


_bot_cache: Dict[str, Bot] = {}
_loop = None


def get_bot(name: str = "chatbot") -> Bot:
    config = get_config()
    if name in _bot_cache:
        return _bot_cache[name]
    bot = Bot.from_config(name, config)
    _bot_cache[name] = bot
    return bot


def try_add_bot(bot: Bot) -> bool:
    if bot.name in _bot_cache:
        return False
    _bot_cache[bot.name] = bot
    return True


def add_bot(bot: Bot) -> None:
    if not try_add_bot(bot):
        raise ValueError(f"bot {bot.name} has existed")


def get_all_bots() -> List[Bot]:
    return list(_bot_cache.values())


def _get_running_loop() -> asyncio.AbstractEventLoop:
    if _loop is None:
        raise RuntimeError("no running loop")
    return _loop


async def async_run() -> None:
    global _loop
    config = get_config()
    _loop = asyncio.get_running_loop()
    reset_message_lock()

    for i in config.bots:
        if i.name in _bot_cache:
            continue
        bot = Bot.from_config(i, config)
        _bot_cache[i.name] = bot
        
    tasks: List[asyncio.Task] = []
    for bot in _bot_cache.values():
        logger.debug(f"run bot {bot.config}")
        tasks.append(_loop.create_task(bot.async_run(config.server)))
    
    if config.server.enable_plugin:  # pragma: no cover
        server = init_server(config.server.listen)
        _loop.call_soon(server.start)
    else:
        server = None
    
    if config.log_level == "DEBUG":
        _loop.set_debug(True)
        
    if not tasks:  # pragma: no cover
        logger.warning("no bot found")
        return
    
    try:
        await asyncio.gather(*tasks)
        logger.info("all bots have been cancelled, exit")
    finally:
        if server is not None:  # pragma: no cover
            logger.info("stop plugin server")
            server.stop(None)
        _loop = None
    

def run() -> None:
    try:
        asyncio.run(async_run())
    except (KeyboardInterrupt, asyncio.CancelledError):  # pragma: no cover
        pass


from .plugin_server import init_server


__all__ = [
    # bot
    "add_bot",
    "try_add_bot",
    "get_bot",
    "async_run",
    "run",
    "Bot",
    # config
    "get_config",
    "init_config",
    "load_config",
    "save_config",
    "Config",
    "BotConfig",
    "ServerConfig",
    # event
    "Event",
    # text
    "Drafty",
    "BaseText",
    "PlainText",
    "Message",
    "TextChain",
    # command
    "CommandCollection",
    "AbstractCommand",
    "AbstractCommandParser",
    "get_collection",
    "BaseSession",
    "MessageSession",
    # decorator
    "on",
    "on_event",
    "on_command",
    # exception
    "KaruhaException"
]
