from google.protobuf import json_format
from tinode_grpc import pb

from .base import BaseServer
from .http import get_session


class WebsocketServer(BaseServer, type="websocket"):
    __slots__ = ["session", "request"]

    WS_ROUTE = "/v0/channels"

    async def start(self) -> None:
        if self._running:  # pragma: no cover
            return await super().start()
        self.session = get_session(self.config)
        self.request = await self.session._ws_connect(self.WS_ROUTE)
        return await super().start()

    async def stop(self) -> None:
        if not self._running:  # pragma: no cover
            return await super().stop()
        await super().stop()
        await self.request.close()
        await self.session.close()
    
    async def send(self, msg: pb.ClientMsg) -> None:
        await self.request.send_str(json_format.MessageToJson(msg))
    
    async def __anext__(self) -> pb.ServerMsg:
        msg = await self.request.receive_bytes()
        return json_format.Parse(msg, pb.ServerMsg())
