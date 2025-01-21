from tinode_grpc import pb

from karuha.version import LIB_VERSION
from karuha.server import GRPCServer, WebsocketServer, get_server_type

from ..utils import AsyncBotOnlineTestCase


class TestServer(AsyncBotOnlineTestCase):
    async def test_server_type(self) -> None:
        self.assertIs(get_server_type("grpc"), GRPCServer)
        self.assertIs(get_server_type("websocket"), WebsocketServer)
        with self.assertRaises(ValueError):
            get_server_type("unknown")

    async def test_grpc(self) -> None:
        async with GRPCServer(self.bot.server_config) as server:
            await server.send(pb.ClientMsg(hi=pb.ClientHi(lang="en", ver=LIB_VERSION)))
            resp = await server.__anext__()
        self.assertTrue(resp.HasField("ctrl"))
        params = resp.ctrl.params
        self.assertIn("ver", params)

    async def test_ws(self) -> None:
        async with WebsocketServer(self.bot.server_config) as server:
            await server.send(pb.ClientMsg(hi=pb.ClientHi(lang="en", ver=LIB_VERSION)))
            resp = await server.__anext__()
        self.assertTrue(resp.HasField("ctrl"))
        params = resp.ctrl.params
        self.assertIn("ver", params)
