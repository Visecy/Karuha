from pathlib import Path
from typing import List, Literal, Optional, Union
from pydantic import AnyUrl, BaseModel, Field, PrivateAttr, validator
from typing_extensions import Annotated

from .logger import logger


class Server(BaseModel):
    host: Annotated[str, AnyUrl] = "localhost:16060"
    ssl: bool = False
    ssl_host: Optional[str] = None
    listen: Annotated[str, AnyUrl] = "0.0.0.0:40051"


class LoginInfo(BaseModel):
    name: str = "chatbot"
    schema_: Literal["basic", "token", "cookie"] = Field(alias="schema")
    secret: str
    user: Optional[str] = None
    authlvl: Optional[str] = None


class Config(BaseModel):
    log_level: str = "INFO"
    server: Server = Server()
    bots: List[LoginInfo] = []
    __path__: Union[str, Path] = PrivateAttr()

    @validator("log_level", always=True)
    def validate_log_level(cls, val: str) -> str:
        logger.setLevel(val)
        return val

    def get_bot(self, name: str = "chatbot") -> LoginInfo:
        for i in self.bots:
            if i.name == name:
                return i
        raise ValueError(f"no bot named '{name}'")
    
    def save(
        self,
        path: Union[str, Path, None] = None,
        *,
        encoding: str = "utf-8",
        ignore_error: bool = False
    ) -> None:
        path = path or self.__path__
        try:
            with open(path, 'w', encoding=encoding) as f:
                f.write(self.json())
        except OSError:
            if not ignore_error:
                raise


_config = None


def get_config() -> Config:
    if _config is None:
        raise ValueError("no config loaded")
    return _config


def load_config(
    path: Union[str, Path] = "config.json",
    *,
    encoding: str = "utf-8",
    auto_create: bool = True
) -> "Config":
    global _config
    try:
        config = Config.parse_file(path, encoding=encoding)
        config.__path__ = path
    except Exception:
        logger.warn(f"failed to load config from '{path}'")
        config = Config(__path__=path)
        if auto_create:
            config.save(encoding=encoding, ignore_error=True)
    _config = config
    return config


def init_config(
    server: Union[dict, Server] = Server(),
    bots: Optional[List[Union[dict, LoginInfo]]] = None,
    log_level: str = "INFO"
) -> Config:
    global _config
    _config = Config(
        server=server,  # type: ignore
        bots=bots,  # type: ignore
        log_level=log_level
    )
    return _config
