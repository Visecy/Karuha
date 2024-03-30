from pathlib import Path
from typing import Iterable, Literal, Optional, Tuple, Union
from pydantic import AnyUrl, BaseModel, Field, PrivateAttr, ValidationError, field_validator
from typing_extensions import Annotated

from .logger import logger, Level


class Server(BaseModel):
    host: Annotated[str, AnyUrl] = "localhost:16060"
    web_host: Annotated[str, AnyUrl] = "localhost:6060"
    api_key: str = "AQEAAAABAAD_rAp4DJh05a1HAwFT3A6K"
    ssl: bool = False
    ssl_host: Optional[str] = None
    enable_plugin: bool = False
    listen: Annotated[str, AnyUrl] = "0.0.0.0:40051"
    timeout: float = 5
    retry: int = 5


class Bot(BaseModel):
    name: str = "chatbot"
    schema_: Literal["basic", "token", "cookie"] = Field(alias="schema")
    secret: str
    auto_subscribe_new_user: bool = False


class Config(BaseModel):
    log_level: Level = "INFO"
    server: Server = Server()
    bots: Tuple[Bot, ...] = ()
    _path: Path = PrivateAttr()

    @field_validator("log_level", mode="after")
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
                f.write(self.model_dump_json(
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
        with open(path, "r", encoding=encoding) as f:
            config = Config.model_validate_json(f.read())
    except OSError:
        logger.warn(f"failed to load file '{path}'", exc_info=True)
        config = Config(_path=path)  # type: ignore
        if auto_create:
            config.save(path, encoding=encoding, ignore_error=True)
    except ValidationError:
        logger.error(f"'{path}' is not valid config file")
        raise
    except Exception:
        logger.error(f"failed to load config from '{path}'")
        raise
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
