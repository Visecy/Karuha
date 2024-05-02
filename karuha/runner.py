"""
A simple Tinode chatbot framework
"""

import asyncio
from typing import Dict, List

from .config import get_config
from .bot import Bot
from .event.sys import SystemStartEvent, SystemStopEvent
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
    
    try:
        await SystemStartEvent.new_and_wait(config, _bot_cache.values())
        if not tasks:  # pragma: no cover
            logger.warning("no bot found, exit")
            return
        await asyncio.gather(*tasks)
        logger.info("all bots have been cancelled, exit")
    finally:
        if server is not None:  # pragma: no cover
            logger.info("stop plugin server")
            server.stop(None)
        await SystemStopEvent(config).trigger(return_exceptions=True)
        _loop = None
    

def run() -> None:
    try:
        asyncio.run(async_run())
    except (KeyboardInterrupt, asyncio.CancelledError):  # pragma: no cover
        pass


from .plugin_server import init_server
