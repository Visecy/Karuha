import asyncio
import contextlib
import signal
import threading
from typing import AsyncGenerator, Dict, List, Optional

from .config import get_config, reset_config
from .bot import Bot, BotState
from .event.sys import SystemStartEvent, SystemStopEvent
from .event.bot import BotFinishEvent, BotReadyEvent
from .logger import logger
from .utils.gathering import DynamicGatheringFuture
from .utils.event_catcher import EventCatcher


_bot_cache: Dict[str, Bot] = {}
_gathering_future: Optional[DynamicGatheringFuture] = None
_runner_lock = threading.Lock()


def try_get_bot(name: str = "chatbot") -> Optional[Bot]:
    try:
        config = get_config()
    except ValueError:  # pragma: no cover
        return

    if name in _bot_cache:
        return _bot_cache[name]

    with contextlib.suppress(Exception):
        bot = Bot.from_config(name, config)
        _bot_cache[name] = bot
        return bot


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
    if bot.state == BotState.stopped and _gathering_future is not None:
        config = get_config()
        logger.debug(f"run bot {bot.config}")
        _gathering_future.add_coroutine(bot.async_run(config.server))
    return True


def add_bot(bot: Bot) -> None:
    if not try_add_bot(bot):
        raise ValueError(f"bot {bot.name} has existed")


def try_remove_bot(bot: Bot) -> bool:
    if bot.name not in _bot_cache:
        return False
    remove_bot(bot)
    return True


def remove_bot(bot: Bot) -> None:
    if bot.name not in _bot_cache:
        raise ValueError(f"bot {bot.name} not found")
    if bot.state == BotState.running:
        bot.cancel()
    del _bot_cache[bot.name]


def get_all_bots() -> List[Bot]:
    return list(_bot_cache.values())


def cancel_all_bots() -> bool:
    return False if _gathering_future is None else _gathering_future.cancel()


@contextlib.asynccontextmanager
async def run_bot(bot: Bot, *, ensure_state: bool = True) -> AsyncGenerator[Bot, None]:
    """run bot temporarily

    :param bot: bot to run
    :type bot: Bot
    :param ensure_state: ensure bot is ready before yield, defaults to True
    :type ensure_state: bool, optional
    :yield: the bot
    :rtype: Generator[Bot, None, None]
    """
    add_bot(bot)
    if ensure_state:
        with EventCatcher(BotReadyEvent) as catcher:
            ev = await catcher.catch_event()
            while ev.bot is not bot:
                ev = await catcher.catch_event()
    try:
        yield bot
    finally:
        remove_bot(bot)
        if ensure_state:
            with EventCatcher(BotFinishEvent) as catcher:
                ev = await catcher.catch_event()
                while ev.bot is not bot:
                    ev = await catcher.catch_event()


def _get_running_loop() -> asyncio.AbstractEventLoop:
    if _gathering_future is None:  # pragma: no cover
        raise RuntimeError("no running loop")
    return _gathering_future.get_loop()


def _handle_sigterm() -> None:  # pragma: no cover
    if _gathering_future is not None:
        _gathering_future.cancel()


async def async_run() -> None:
    global _gathering_future

    config = get_config()
    loop = asyncio.get_running_loop()
    with contextlib.suppress(NotImplementedError):
        loop.add_signal_handler(signal.SIGTERM, _handle_sigterm)

    for i in config.bots:
        if i.name in _bot_cache:
            continue
        bot = Bot.from_config(i, config)
        _bot_cache[i.name] = bot

    if not _runner_lock.acquire(blocking=False):
        raise RuntimeError("another runner is running")
    
    tasks: List[asyncio.Future] = []
    server = None
    try:
        for bot in _bot_cache.values():
            logger.debug(f"run bot {bot.config}")
            tasks.append(loop.create_task(bot.async_run(config.server)))

        if config.server.enable_plugin:  # pragma: no cover
            server = init_server(config.server.listen)
            loop.call_soon(server.start)

        if config.log_level == "DEBUG":
            loop.set_debug(True)
        await SystemStartEvent.new_and_wait(config, _bot_cache.values())
        if not tasks:  # pragma: no cover
            logger.warning("no bot found, exit")
            return
        _gathering_future = DynamicGatheringFuture(tasks, loop=loop)
        await _gathering_future
        logger.info("all bots have been cancelled, exit")
    finally:
        if server is not None:  # pragma: no cover
            logger.info("stop plugin server")
            server.stop(None)
        try:
            await SystemStopEvent(config).trigger(return_exceptions=True)
        finally:
            _gathering_future = None
            _runner_lock.release()


def run() -> None:  # pragma: no cover
    with contextlib.suppress(KeyboardInterrupt, asyncio.CancelledError):
        asyncio.run(async_run())


def reset() -> None:
    global _bot_cache
    _bot_cache = {}
    reset_config()


from .plugin_server import init_server
