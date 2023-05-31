import logging
import os
import sys
from pathlib import Path
from time import asctime, localtime
from typing import IO, TextIO, Union, cast

formatter = logging.Formatter('[%(asctime)s %(name)s][%(levelname)s] %(message)s')


def s_open(path: Union[str, bytes, os.PathLike], mode: str, **kwds) -> IO:
    base, _ = os.path.split(path)  # type: ignore
    if base and not os.path.isdir(base):
        os.makedirs(base)
    return open(path, mode, **kwds)


def add_log_stream(logger: logging.Logger, stream: TextIO) -> None:
    handler = logging.StreamHandler(stream)
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
            os.rename(file_path, log_dir / f"{asctime(m_time).replace(':', '-')}.log")
    add_log_stream(logger, cast(TextIO, s_open(file_path, "a", encoding="utf-8")))


def get_logger(name: str = "KARUHA", dir: Union[str, os.PathLike, None] = None) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    add_log_stream(logger, sys.stdout)
    if dir:
        add_log_dir(logger, dir)
    return logger


logger = get_logger()


__all__ = [
    'logger',
]
