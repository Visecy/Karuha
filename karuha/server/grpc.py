import sys
from asyncio import Queue
from typing import AsyncGenerator

import grpc
from tinode_grpc import pb

from .base import BaseServer


class GRPCServer(BaseServer, type="grpc"):
    __slots__ = ["channel", "client", "queue"]

    async def start(self) -> None:
        is_running = self._running
        await super().start()
        if is_running:  # pragma: no cover
            return

        self.queue = Queue()
        self.channel = self._get_channel()
        stream = get_stream(self.channel)
        self.client: grpc.aio.StreamStreamCall[pb.ClientMsg, pb.ServerMsg] = stream(self._message_generator())

    async def stop(self) -> None:
        is_running = self._running
        await super().stop()
        if not is_running:  # pragma: no cover
            return

        if hasattr(self, "channel"):
            await self.channel.close()

    async def send(self, msg: pb.ClientMsg) -> None:
        self._ensure_running()
        await self.queue.put(msg)

    async def __anext__(self) -> pb.ServerMsg:
        self._ensure_running()
        try:
            msg = await self.client.read()
        except grpc.RpcError as e:  # pragma: no cover
            self.logger.error("gRPC server error", exc_info=sys.exc_info())
            raise self.exc_type(e) from e
        if msg == grpc.aio.EOF:  # pragma: no cover
            self.logger.info("server closed connection")
            raise StopAsyncIteration(msg)
        self.logger.debug(f"in: {msg}")
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
        opts = (("grpc.ssl_target_name_override", ssl_host),) if ssl_host else None
        self.logger.info(f"connecting to secure server at {host} SNI={ssl_host or host}")
        return grpc.aio.secure_channel(host, grpc.ssl_channel_credentials(), opts)


def get_stream(channel: grpc.aio.Channel, /) -> grpc.aio.StreamStreamMultiCallable:  # pragma: no cover
    return channel.stream_stream(
        "/pbx.Node/MessageLoop",
        request_serializer=pb.ClientMsg.SerializeToString,
        response_deserializer=pb.ServerMsg.FromString,
    )
