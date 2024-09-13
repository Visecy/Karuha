import asyncio
import contextlib
import signal
from typing import Dict, List, MutableSequence, Optional, Awaitable

from .config import get_config
from .bot import Bot, BotState
from .event.sys import SystemStartEvent, SystemStopEvent
from .logger import logger


_bot_cache: Dict[str, Bot] = {}
_gathering_future: Optional["DynamicGatheringFuture"] = None


class DynamicGatheringFuture(asyncio.Future):
    """
    A dynamic version of `asyncio.tasks._GatheringFuture`.

    It allows to add new tasks to the gathering future.
    """

    __slots__ = ["children", "nfinished", "_cancel_requested"]

    def __init__(self, children: MutableSequence[asyncio.Future], *, loop=None):
        super().__init__(loop=loop)
        self.children = children
        self.nfinished = 0
        self._cancel_requested = False
        for child in children:
            child.add_done_callback(self._done_callback)

    def add_task(self, fut: asyncio.Future) -> None:
        if self.done():  # pragma: no cover
            raise RuntimeError("cannot add child to cancelled parent")
        fut.add_done_callback(self._done_callback)
        self.children.append(fut)

    def add_coroutine(self, coro: Awaitable) -> None:
        fut = asyncio.ensure_future(coro)
        if fut is not coro:
            # 'coro' was not a Future, therefore, 'fut' is a new
            # Future created specifically for 'coro'.  Since the caller
            # can't control it, disable the "destroy pending task"
            # warning.
            fut._log_destroy_pending = False  # type: ignore[attr-defined]
        self.add_task(fut)
    
    def cancel(self, msg=None) -> bool:  # pragma: no cover
        if self.done():
            return False
        ret = False
        for child in self.children:
            canceled = child.cancel(msg=msg) if msg is None else child.cancel()  # type: ignore
            if canceled:
                ret = True
        if ret:
            # If any child tasks were actually cancelled, we should
            # propagate the cancellation request regardless of
            # *return_exceptions* argument.  See issue 32684.
            self._cancel_requested = True
        return ret

    def _done_callback(self, fut: asyncio.Future) -> None:
        self.nfinished += 1

        if self.done():  # pragma: no cover
            if not fut.cancelled():
                # Mark exception retrieved.
                fut.exception()
            return

        if fut.cancelled():
            # Check if 'fut' is cancelled first, as
            # 'fut.exception()' will *raise* a CancelledError
            # instead of returning it.
            exc = asyncio.CancelledError()
            self.set_exception(exc)
            return
        else:
            exc = fut.exception()
            if exc is not None:  # pragma: no cover
                self.set_exception(exc)
                return

        if self.nfinished == len(self.children):
            # All futures are done; create a list of results
            # and set it to the 'outer' future.
            results = []

            for fut in self.children:
                if fut.cancelled():  # pragma: no cover
                    # Check if 'fut' is cancelled first, as
                    # 'fut.exception()' will *raise* a CancelledError
                    # instead of returning it.
                    res = asyncio.CancelledError()
                else:
                    res = fut.exception()
                    if res is None:
                        res = fut.result()
                results.append(res)

            if self._cancel_requested:  # pragma: no cover
                # If gather is being cancelled we must propagate the
                # cancellation regardless of *return_exceptions* argument.
                # See issue 32684.
                self.set_exception(asyncio.CancelledError())
            else:
                self.set_result(results)


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


def remove_bot(bot: Bot) -> None:
    if bot.name not in _bot_cache:
        raise ValueError(f"bot {bot.name} not found")
    if bot.state == BotState.running:
        bot.cancel()
    del _bot_cache[bot.name]


def get_all_bots() -> List[Bot]:
    return list(_bot_cache.values())


def _get_running_loop() -> asyncio.AbstractEventLoop:
    if _gathering_future is None:  # pragma: no cover
        raise RuntimeError("no running loop")
    return _gathering_future.get_loop()


def _handle_sigterm() -> None:  # pragma: no cover
    for bot in _bot_cache.values():
        bot.cancel()


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

    tasks: List[asyncio.Future] = []
    for bot in _bot_cache.values():
        logger.debug(f"run bot {bot.config}")
        tasks.append(loop.create_task(bot.async_run(config.server)))

    if config.server.enable_plugin:  # pragma: no cover
        server = init_server(config.server.listen)
        loop.call_soon(server.start)
    else:
        server = None

    if config.log_level == "DEBUG":
        loop.set_debug(True)

    try:
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
        await SystemStopEvent(config).trigger(return_exceptions=True)
        _gathering_future = None


def run() -> None:  # pragma: no cover
    with contextlib.suppress(KeyboardInterrupt, asyncio.CancelledError):
        asyncio.run(async_run())


from .plugin_server import init_server
