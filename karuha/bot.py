import asyncio
from asyncio.queues import Queue
from enum import IntEnum
from typing import AsyncGenerator, Literal
from google.protobuf.message import Message

from .config import LoginSecret, Server
from .logger import logger
from .stream import get_channel, get_stream


class State(IntEnum):
    disabled = 0
    running = 1
    stopped = 2


class KaruhaBot(object):
    __slots__ = ["_info", "queue", "state"]

    def __init__(
        self,
        name: str,
        schema: Literal["basic", "token", "cookie"],
        secret: str
    ) -> None:
        self._info = LoginSecret(name=name, schema=schema, secret=secret)
        self.queue = Queue()
        self.state = State.stopped
    
    @property
    def name(self) -> str:
        return self._info.name
    
    async def _message_loop(self) -> AsyncGenerator[Message, None]:
        while True:
            msg: Message = await self.queue.get()
            logger.debug(f"out: {msg}")
            yield msg
    
    async def _run(self, server: Server) -> None:
        assert self.state != State.disabled
        self.state = State.running
        async with get_channel(server.host, server.ssl, server.ssl_host) as channel:
            stream = get_stream(channel)
            client = stream(self._message_loop())
            async for msg in client:
                logger.debug(f"in {msg}")
        self.state = State.stopped
    
    def run(self, server: Server) -> None:
        asyncio.run(self._run(server))
