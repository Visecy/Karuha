import base64
from io import BytesIO

from tinode_grpc import pb

from karuha.utils.decode import _encode_params, dict2msg

from .utils import AsyncBotTestCase


class TestServer(AsyncBotTestCase):
    def test_decode(self) -> None:
        raw_data = {"ctrl": {"id": "123", "code": 200, "params": {"foo": "bar"}}}
        data = _encode_params(raw_data, pb.ServerMsg.DESCRIPTOR)
        self.assertEqual(data, {"ctrl": {"id": "123", "code": 200, "params": {"foo": base64.b64encode(b"\"bar\"")}}})
        msg = dict2msg(raw_data, pb.ServerMsg)
        self.assertEqual(msg.ctrl.id, "123")
        self.assertEqual(msg.ctrl.code, 200)
        self.assertEqual(msg.ctrl.params["foo"], b"\"bar\"")

    async def test_run(self) -> None:
        server = self.bot.server
        self.assertTrue(server.running)
        async with server:
            self.assertTrue(server.running)
        self.assertFalse(server.running)
        await server.stop()
        self.assertFalse(server.running)
        await server.start()
        self.assertTrue(server.running)
    
    async def test_mock_upload(self) -> None:
        content = b"test"
        tid1, params = await self.bot.upload(BytesIO(content))
        url = params["url"]
        self.assertIn("/v0/file/s/", url)
        download_file = BytesIO()
        tid2, size = await self.bot.download(url, download_file)
        self.assertNotEqual(tid1, tid2)
        self.assertEqual(size, len(content))
        self.assertEqual(download_file.getvalue(), content)
