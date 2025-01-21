import os
from io import IOBase
from typing import BinaryIO, Optional, Union

from aiofiles import open as aio_open
from aiofiles.threadpool.binary import AsyncBufferedIOBase
from aiohttp import ClientSession, ClientTimeout, FormData
from tinode_grpc import pb

from ..config import Server as ServerConfig
from ..exception import KaruhaServerError
from ..utils.context import nullcontext
from ..utils.decode import dict2msg, load_json
from ..version import APP_VERSION, LIB_VERSION


def get_session(config: ServerConfig, auth: Optional[str] = None) -> ClientSession:
    headers = {
        "X-Tinode-APIKey": config.api_key,
        "User-Agent": f"KaruhaBot {APP_VERSION}/{LIB_VERSION}"
    }
    if auth:
        headers["X-Tinode-Auth"] = auth
    return ClientSession(
        str(config.web_host),
        headers=headers,
        timeout=ClientTimeout(total=config.timeout),
    )


async def upload_file(
    session: ClientSession,
    url: str,
    path: Union[str, os.PathLike, BinaryIO],
    *,
    tid: Optional[str] = None,
    filename: Optional[str] = None
) -> pb.ServerCtrl:
    data = FormData()
    if tid is not None:
        data.add_field("id", tid)
    if isinstance(path, (BinaryIO, IOBase)):
        path.seek(0)
        cm = nullcontext(path)
    else:
        cm = open(path, "rb")
        filename = filename or os.path.basename(path)
    with cm as f:
        data.add_field("file", f, filename=filename)
        async with session.post(url, data=data) as resp:
            resp.raise_for_status()
            ret = await resp.text()
    msg = dict2msg(load_json(ret), pb.ServerMsg, ignore_unknown_fields=True)
    ctrl = msg.ctrl
    if tid is not None and ctrl.id != tid:  # pragma: no cover
        raise KaruhaServerError("tid mismatch")
    return ctrl


async def download_file(
    session: ClientSession,
    url: str,
    path: Union[str, os.PathLike, BinaryIO],
    *,
    tid: Optional[str] = None
) -> int:
    if isinstance(path, (BinaryIO, IOBase)):
        path.seek(0)
        cm = nullcontext(path)
    else:
        cm = aio_open(path, "wb")
    size = 0
    async with session.get(url, params={"id": tid}) as resp, cm as f:
        resp.raise_for_status()
        async for chunk in resp.content.iter_any():
            size += len(chunk)
            if isinstance(f, AsyncBufferedIOBase):
                await f.write(chunk)
            else:
                f.write(chunk)
    return size
