from abc import ABC, abstractmethod
from logging import Logger
import os
from typing import Any, BinaryIO, ClassVar, Dict, Optional, Type, Union
from aiohttp import ClientConnectionError
from typing_extensions import Self
from tinode_grpc import pb

from ..logger import logger as global_logger
from ..config import Server as ServerConfig
from .http import get_session, upload_file, download_file


_server_types: Dict[str, Type["BaseServer"]] = {}


def get_server_type(type: str) -> Type["BaseServer"]:
    if type not in _server_types:
        raise ValueError(f"unknown server type {type}")
    return _server_types[type]


class BaseServer(ABC):
    __slots__ = ["config", "logger", "_running"]

    type: ClassVar[str] = "generic"

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
        self,
        path: Union[str, os.PathLike, BinaryIO],
        *,
        tid: Optional[str] = None,
        filename: Optional[str] = None
    ) -> pb.ServerCtrl:
        url = self.UPLOAD_ROUTE
        retry = self.config.retry or 1
        async with get_session(self.config) as session:
            while True:
                try:
                    ctrl = await upload_file(session, url, path, tid=tid, filename=filename)
                    self.logger.info(f"uploaded {path} to {url}")
                    return ctrl
                except ClientConnectionError as e:
                    err_text = f"fail to upload file {path}: {e} (retry {retry} times)"
                    self.logger.error(err_text, exc_info=True)
                    if retry <= 0:
                        raise
                retry -= 1

    async def download(
        self,
        url: str,
        path: Union[str, os.PathLike, BinaryIO],
        *,
        tid: Optional[str] = None
    ) -> int:
        retry = self.config.retry or 1
        async with get_session(self.config) as session:
            while True:
                try:
                    size = await download_file(session, url, path, tid=tid)
                    self.logger.info(f"downloaded {size} bytes from {url}")
                    return size
                except ClientConnectionError as e:
                    err_text = f"fail to download file {url}: {e} (retry {retry} times)"
                    self.logger.error(err_text, exc_info=True)
                    if retry <= 0:
                        raise
                retry -= 1
    
    async def __aenter__(self) -> Self:
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()
    
    async def __aiter__(self) -> Self:
        return self
    
    @abstractmethod
    async def __anext__(self) -> pb.ServerMsg:
        raise NotImplementedError
    
    def __repr__(self) -> str:
        if self._running:
            return f"<karuha.server {self.type} {self.config} running>"
        else:
            return f"<karuha.server {self.type} {self.config} stopped>"
    
    def __init_subclass__(cls, *, type: Optional[str] = None, **kwds: Any) -> None:
        if type is not None:
            cls.type = type
            _server_types[type] = cls
        return super().__init_subclass__(**kwds)
