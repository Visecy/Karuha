from asyncio import Queue
from typing import AsyncGenerator

import grpc
from tinode_grpc import pb

from .base import BaseServer


class GRPCServer(BaseServer, type="grpc"):
    __slots__ = ["channel", "client", "queue"]

    async def start(self) -> None:
        if self._running:  # pragma: no cover
            return await super().start()
        self.queue = Queue()
        self.channel = self._get_channel()
        stream = get_stream(self.channel)
        self.client: grpc.aio.StreamStreamCall[pb.ClientMsg, pb.ServerMsg] = stream(self._message_generator())
        return await super().start()
    
    async def stop(self) -> None:
        if not self._running:  # pragma: no cover
            return await super().stop()
        await super().stop()
        await self.channel.close()
    
    async def send(self, msg: pb.ClientMsg) -> None:
        await self.queue.put(msg)
    
    async def __anext__(self) -> pb.ServerMsg:
        msg = await self.client.read()
        if msg == grpc.aio.EOF:  # pragma: no cover
            self.logger.info("server closed connection")
            raise StopAsyncIteration(msg)
        return msg

    async def _message_generator(self) -> AsyncGenerator[pb.ClientMsg, None]:  # pragma: no cover
        while self._running:
            msg: pb.ClientMsg = await self.queue.get()
            self.logger.debug(f"out: {msg}")
            yield msg

    def _get_channel(self) -> grpc.aio.Channel:
        host = self.config.host
        secure = self.config.ssl
        ssl_host = self.config.ssl_host
        if not secure:
            self.logger.info(f"connecting to server at {host}")
            return grpc.aio.insecure_channel(host)
        opts = (('grpc.ssl_target_name_override', ssl_host),) if ssl_host else None
        self.logger.info(f"connecting to secure server at {host} SNI={ssl_host or host}")
        return grpc.aio.secure_channel(host, grpc.ssl_channel_credentials(), opts)


def get_stream(channel: grpc.aio.Channel, /) -> grpc.aio.StreamStreamMultiCallable:  # pragma: no cover
    return channel.stream_stream(
        '/pbx.Node/MessageLoop',
        request_serializer=pb.ClientMsg.SerializeToString,
        response_deserializer=pb.ServerMsg.FromString
    )
