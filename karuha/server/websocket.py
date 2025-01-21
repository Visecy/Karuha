from tinode_grpc import pb
from pydantic_core import to_json, from_json

from .base import BaseServer
from .http import get_session
from ..utils.decode import dict2msg, msg2dict


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
        data = msg2dict(msg)
        await self.request.send_bytes(to_json(data))
    
    async def __anext__(self) -> pb.ServerMsg:
        msg = await self.request.receive_str()
        return dict2msg(from_json(msg), pb.ServerMsg, ignore_unknown_fields=True)
