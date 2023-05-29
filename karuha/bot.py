import asyncio
from asyncio.queues import Queue
from enum import IntEnum
from typing import Any, AsyncGenerator, Dict, Literal, Optional
from google.protobuf.message import Message
from tinode_grpc import pb

from .config import LoginSecret, Server, get_config
from .logger import logger
from .stream import get_channel, get_stream
from .event import get_server_event


class State(IntEnum):
    disabled = 0
    running = 1
    stopped = 2


class Bot(object):
    __slots__ = ["queue", "state", "client", "login_info", "_wait_list", "_tid_counter"]

    def __init__(
        self,
        name: str,
        schema: Literal["basic", "token", "cookie"],
        secret: str
    ) -> None:
        self.login_info = LoginSecret(name=name, schema=schema, secret=secret)
        self.queue = Queue()
        self.state = State.stopped
        self._wait_list: Dict[str, asyncio.Future] = {}
        self._tid_counter = 100
    
    async def send_message(self, wait_tid: Optional[str] = None, **kwds: Message) -> Any:
        client_msg = pb.ClientMsg(**kwds)
        if wait_tid is None:
            return await self.queue.put(client_msg)
        future = asyncio.get_running_loop().create_future()
        self._wait_list[wait_tid] = future
        try:
            await self.queue.put(client_msg)
            ctrl = await future
        except:
            self._wait_list.pop(wait_tid, None)
            raise
        else:
            assert self._wait_list.pop(wait_tid) == future
        if ctrl.code < 200 or ctrl.code >= 400:
            logger.error(f"{ctrl.text} when sending message {client_msg}")
        return ctrl.params

    async def async_run(self, server: Server) -> None:
        assert self.state == State.stopped
        async with get_channel(server.host, server.ssl, server.ssl_host) as channel:
            stream = get_stream(channel)
            self.client = stream(self._message_generator())
            await self._loop()
    
    def run(self, server: Optional[Server] = None) -> None:
        server = server or get_config().server
        asyncio.run(self.async_run(server))
    
    def cancel(self) -> None:
        if self.state != State.running:
            return
        for i in self._wait_list.values():
            i.cancel()
        self.state = State.stopped

    @property
    def name(self) -> str:
        return self.login_info.name
    
    async def _message_generator(self) -> AsyncGenerator[Message, None]:
        while True:
            msg: Message = await self.queue.get()
            logger.debug(f"out: {msg}")
            yield msg
    
    async def _loop(self) -> None:
        self.state = State.running
        try:
            message: pb.ServerMsg
            async for message in self.client:  # type: ignore
                logger.debug(f"in {message}")
                for desc, msg in message.ListFields():
                    for e in get_server_event(desc.name):
                        asyncio.create_task(
                            e(self, msg)()
                        )
        finally:
            self.cancel()
    