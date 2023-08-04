from pathlib import Path
from typing import Iterable, Literal, Optional, Tuple, Union
from pydantic import AnyUrl, BaseModel, Field, PrivateAttr, validator
from typing_extensions import Annotated

from .logger import logger, Level


class Server(BaseModel):
    host: Annotated[str, AnyUrl] = "localhost:16060"
    ssl: bool = False
    ssl_host: Optional[str] = None
    listen: Annotated[str, AnyUrl] = "0.0.0.0:40051"


class Bot(BaseModel):
    name: str = "chatbot"
    schema_: Literal["basic", "token", "cookie"] = Field(alias="schema")
    secret: str
    user: Optional[str] = None


class Config(BaseModel):
    log_level: Level = "INFO"
    server: Server = Server()
    bots: Tuple[Bot, ...] = ()
    _path: Path = PrivateAttr()

    @validator("log_level", always=True)
    def validate_log_level(cls, val: str) -> str:
        logger.setLevel(val)
        return val

    def save(
        self,
        path: Union[str, Path, None] = None,
        *,
        encoding: str = "utf-8",
        ignore_error: bool = False
    ) -> None:
        path = path or self._path
        try:
            with open(path, 'w', encoding=encoding) as f:
                f.write(self.json(
                    indent=4, by_alias=True, exclude_defaults=False
                ))
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
    except Exception:
        logger.warn(f"failed to load config from '{path}'")
        config = Config(_path=path)  # type: ignore
        if auto_create:
            config.save(path, encoding=encoding, ignore_error=True)
    config._path = path  # type: ignore
    _config = config
    return config


def init_config(
    server: Union[dict, Server] = Server(),
    bots: Optional[Iterable[Union[dict, Bot]]] = None,
    log_level: Level = "INFO"
) -> Config:
    global _config
    _config = Config(
        server=server,  # type: ignore
        bots=bots or (),  # type: ignore
        log_level=log_level
    )
    return _config


def save_config() -> Path:
    config = get_config()
    config.save()
    return config._path
