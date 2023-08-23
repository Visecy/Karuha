import logging
from logging import LogRecord
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Union

from . import WORKDIR


Level = Union[int, str]
formatter = logging.Formatter('[%(asctime)s %(name)s][%(levelname)s] %(message)s')


class NameFilter(logging.Filter):
    def filter(self, record: LogRecord) -> bool:
        if not self.name:
            return True
        return record.name == self.name


def add_log_dir(logger: logging.Logger, log_dir: Union[str, os.PathLike]) -> None:
    log_dir = Path(log_dir)
    file_path = log_dir / "latest.log"
    log_dir.mkdir(exist_ok=True, parents=True)
    handler = TimedRotatingFileHandler(
        file_path,
        when="D",
        backupCount=64,
        encoding="utf-8"
    )
    handler.setFormatter(formatter)
    handler.addFilter(NameFilter(logger.name))
    logger.addHandler(handler)


def get_sub_logger(name: str) -> logging.Logger:
    sub_logger = logger.getChild(name)
    add_log_dir(sub_logger, WORKDIR / name / "log")
    return sub_logger


logger = logging.getLogger("Karuha")
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
add_log_dir(logger, WORKDIR / "log")


__all__ = [
    'logger',
]
