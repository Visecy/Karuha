import logging
import os
from pathlib import Path
from time import asctime, localtime
from typing import Union

from . import WORKDIR

Level = Union[int, str]
formatter = logging.Formatter('[%(asctime)s %(name)s][%(levelname)s] %(message)s')


def add_log_handler(logger: logging.Logger, handler: logging.Handler) -> None:
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def add_log_dir(logger: logging.Logger, log_dir: Union[str, os.PathLike]) -> None:
    log_dir = Path(log_dir)
    file_path = log_dir / "latest.log"
    if file_path.is_file():
        stat = log_dir.stat()
        m_time = localtime(stat.st_mtime)
        n_time = localtime()
        if (
            m_time.tm_mday != n_time.tm_mday or
            m_time.tm_mon != n_time.tm_mon or
            m_time.tm_year != n_time.tm_year
        ):
            file_path.rename(log_dir / f"{asctime(m_time).replace(':', '-')}.log")
    
    log_dir.mkdir(exist_ok=True, parents=True)
    add_log_handler(logger, logging.FileHandler(file_path, encoding="utf-8"))


def get_sub_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(f"Karuha.{name}")
    add_log_dir(logger, WORKDIR / name / "log")
    return logger


logger = logging.getLogger("Karuha")
logger.setLevel(logging.INFO)
add_log_handler(logger, logging.StreamHandler())
add_log_dir(logger, WORKDIR / "log")


__all__ = [
    'logger',
]
