import asyncio
import sys

from aiohttp import ClientConnectionError, WebSocketError, WSServerHandshakeError
from pydantic_core import from_json, to_json
from tinode_grpc import pb

from ..utils.decode import dict2msg, msg2dict
from .base import BaseServer
from .http import get_session


class WebsocketServer(BaseServer, type="websocket"):
    __slots__ = ["session", "request"]

    WS_ROUTE = "/v0/channels"

    async def start(self) -> None:
        is_running = self._running
        await super().start()
        if is_running:  # pragma: no cover
            return

        try:
            self.session = get_session(self.config)
            self.request = await self.session._ws_connect(self.WS_ROUTE)
        except (WSServerHandshakeError, ClientConnectionError) as e:
            self.logger.error("websocket handshake error", exc_info=True)
            await self.stop()
            raise self.exc_type("websocket handshake error") from e
        except asyncio.TimeoutError as e:  # pragma: no cover
            self.logger.error("websocket handshake timeout", exc_info=True)
            await self.stop()
            raise self.exc_type("websocket handshake timeout") from e

    async def stop(self) -> None:
        is_running = self._running
        await super().stop()
        if not is_running:  # pragma: no cover
            return

        if hasattr(self, "request"):
            await self.request.close()
        if hasattr(self, "session"):
            await self.session.close()

    async def send(self, msg: pb.ClientMsg) -> None:
        self._ensure_running()
        data = msg2dict(msg)
        self.logger.debug(f"out: {to_json(data, indent=4).decode()}")
        try:
            await self.request.send_str(to_json(data).decode())
        except WebSocketError as e:  # pragma: no cover
            self.logger.error("websocket send error", exc_info=sys.exc_info())
            raise self.exc_type("websocket send error") from e

    async def __anext__(self) -> pb.ServerMsg:
        self._ensure_running()
        try:
            msg = await self.request.receive_str()
            data = from_json(msg)
        except WebSocketError as e:  # pragma: no cover
            self.logger.error("websocket receive error", exc_info=sys.exc_info())
            raise self.exc_type("websocket receive error") from e
        self.logger.debug(f"in: {to_json(data, indent=4).decode()}")
        return dict2msg(data, pb.ServerMsg, ignore_unknown_fields=True)
