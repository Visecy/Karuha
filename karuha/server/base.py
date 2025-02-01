from abc import ABC, abstractmethod
from logging import Logger
import os
from typing import Any, BinaryIO, ClassVar, Dict, Optional, Type, Union
from aiohttp import ClientConnectionError, ClientError
from typing_extensions import Self
from tinode_grpc import pb

from ..exception import KaruhaServerError

from ..logger import logger as global_logger
from ..config import Server as ServerConfig
from ..utils.decode import decode_mapping
from .http import get_session, upload_file, download_file


_server_types: Dict[str, Type["BaseServer"]] = {}


def get_server_type(type: str) -> Type["BaseServer"]:
    if type not in _server_types:  # pragma: no cover
        raise ValueError(f"unknown server type {type}")
    return _server_types[type]


class BaseServer(ABC):
    __slots__ = ["config", "logger", "_running"]

    type: ClassVar[str] = "generic"
    exc_type: ClassVar[Type[Exception]] = KaruhaServerError

    UPLOAD_ROUTE = "/v0/file/u/"

    def __init__(self, config: ServerConfig, logger: Optional[Logger] = None) -> None:
        self.config = config
        self.logger = logger or global_logger
        self._running = False

    async def start(self) -> None:
        if self._running:
            self.logger.warning(f"server {self.type} already running")
            return
        self._running = True

    async def stop(self) -> None:
        if not self._running:
            self.logger.warning(f"server {self.type} already stopped")
            return
        self._running = False

    @abstractmethod
    async def send(self, msg: pb.ClientMsg) -> None:
        raise NotImplementedError

    async def upload(
        self, path: Union[str, os.PathLike, BinaryIO], auth: str, *, tid: Optional[str] = None, filename: Optional[str] = None
    ) -> Dict[str, Any]:
        url = self.UPLOAD_ROUTE
        retry = self.config.retry or 1
        async with get_session(self.config, auth) as session:
            while True:
                try:
                    ctrl = await upload_file(session, url, path, tid=tid, filename=filename)
                    self.logger.info(f"uploaded {path} to {url}")
                    self.logger.debug(f"uploaded response: {ctrl}")
                    return decode_mapping(ctrl.params)
                except ClientConnectionError as e:
                    err_text = f"fail to upload file {path}: {e} ({retry=})"
                    self.logger.error(err_text, exc_info=True)
                    if retry <= 0:
                        raise KaruhaServerError(err_text) from e
                except ClientError as e:  # pragma: no cover
                    err_text = f"fail to upload file {path}: {e}"
                    self.logger.error(err_text, exc_info=True)
                    raise KaruhaServerError(err_text) from e
                retry -= 1

    async def download(
        self, url: str, path: Union[str, os.PathLike, BinaryIO], auth: str, *, tid: Optional[str] = None
    ) -> int:
        retry = self.config.retry or 1
        async with get_session(self.config, auth) as session:
            while True:
                try:
                    size = await download_file(session, url, path, tid=tid)
                    self.logger.info(f"downloaded {size} bytes from {url}")
                    return size
                except ClientConnectionError as e:
                    err_text = f"fail to download file {url}: {e} ({retry=})"
                    self.logger.error(err_text, exc_info=True)
                    if retry <= 0:
                        raise KaruhaServerError(err_text) from e
                except ClientError as e:  # pragma: no cover
                    err_text = f"fail to download file {url}: {e}"
                    self.logger.error(err_text, exc_info=True)
                    raise KaruhaServerError(err_text) from e
                retry -= 1

    @property
    def running(self) -> bool:
        return self._running

    def _ensure_running(self) -> None:
        if not self._running:
            raise self.exc_type("server not running")

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()

    def __aiter__(self) -> Self:
        return self

    @abstractmethod
    async def __anext__(self) -> pb.ServerMsg:
        raise NotImplementedError

    def __init_subclass__(cls, *, type: Optional[str] = None, **kwds: Any) -> None:
        if type is not None:
            cls.type = type
            _server_types[type] = cls
        return super().__init_subclass__(**kwds)

    def __repr__(self) -> str:
        if self._running:
            return f"<karuha.server {self.type} {self.config} running>"
        else:
            return f"<karuha.server {self.type} {self.config} stopped>"
