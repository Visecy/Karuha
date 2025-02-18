import logging
import os
from logging import LogRecord
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
import sys
from typing import TextIO, Union

from . import WORKDIR


Level = Union[int, str]
formatter = logging.Formatter('[%(asctime)s %(name)s][%(levelname)s] %(message)s')


class NameFilter(logging.Filter):
    def filter(self, record: LogRecord) -> bool:
        if not self.name:  # pragma: no cover
            return True
        return record.name == self.name


class _StderrHandler(logging.StreamHandler):
    """
    This class is like a StreamHandler using sys.stderr, but always uses
    whatever sys.stderr is currently set to rather than the value of
    sys.stderr at handler construction time.
    """
    def __init__(self, level: "logging._Level" = logging.NOTSET):
        """
        Initialize the handler.
        """
        super(logging.StreamHandler, self).__init__(level)

    @property
    def stream(self) -> TextIO:
        return sys.stderr

def add_log_dir(logger: logging.Logger, log_dir: Union[str, os.PathLike]) -> None:
    log_dir = Path(log_dir)
    name = logger.name
    if '.' not in name:
        file_path = log_dir / "main.log"
    else:
        _, bot_name = name.split('.')
        file_path = log_dir / f"bot_{bot_name}.log"
    log_dir.mkdir(exist_ok=True, parents=True)
    handler = TimedRotatingFileHandler(
        file_path,
        when="D",
        backupCount=64,
        encoding="utf-8"
    )
    handler.setFormatter(formatter)
    handler.addFilter(NameFilter(name))
    logger.addHandler(handler)


def get_sub_logger(name: str) -> logging.Logger:
    sub_logger = logger.getChild(name)
    add_log_dir(sub_logger, WORKDIR / "log")
    return sub_logger


logger = logging.getLogger("Karuha")
logger.setLevel(logging.INFO)
console_handler = _StderrHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
add_log_dir(logger, WORKDIR / "log")


__all__ = [
    'logger',
]
