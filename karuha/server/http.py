import base64
from io import IOBase
import os
from typing import BinaryIO, Optional, Tuple, Union

from aiofiles import open as aio_open
from aiofiles.threadpool.binary import AsyncBufferedIOBase
from aiohttp import ClientSession, ClientTimeout, FormData
from pydantic_core import from_json
from tinode_grpc import pb
from google.protobuf import json_format

from ..exception import KaruhaServerError
from ..config import Server as ServerConfig
from ..version import APP_VERSION, LIB_VERSION
from ..utils.context import nullcontext


async def read_auth_cookie(cookie_file_name: Union[str, bytes, os.PathLike]) -> Tuple[str, Union[str, bytes]]:
    """Read authentication token from a file"""
    async with aio_open(cookie_file_name, 'r') as cookie:
        params = from_json(await cookie.read())
    schema = params.get("schema")
    secret = params.get('secret')
    if schema is None or secret is None:
        raise ValueError("invalid cookie file")
    if schema == 'token':
        secret = base64.b64decode(secret)
    return schema, secret


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
    ctrl = json_format.Parse(ret, pb.ServerCtrl())
    if ctrl.id != tid:
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
