import logging
import os
import sys
from time import localtime, asctime
from typing import TextIO, Union, IO, cast

from . import WORKDIR


logger = logging.getLogger('KARUHA')
formatter = logging.Formatter('[%(asctime)s %(name)s][%(levelname)s] %(message)s')


def s_open(path: Union[str, bytes, os.PathLike], mode: str, **kwds) -> IO:
    base, _ = os.path.split(path)  # type: ignore
    if base and not os.path.isdir(base):
        os.makedirs(base)
    return open(path, mode, **kwds)


def add_log_file(stream: Union[str, TextIO]) -> None:
    if isinstance(stream, str):
        if os.path.isfile(stream):
            stat = os.stat(stream)
            m_time = localtime(stat.st_mtime)
            n_time = localtime()
            if (
                m_time.tm_mday != n_time.tm_mday or
                m_time.tm_mon != n_time.tm_mon or
                m_time.tm_year != n_time.tm_year
            ):
                os.rename(stream, f"{WORKDIR}/log/{asctime(m_time).replace(':', '-')}.log")
        stream = cast(TextIO, s_open(stream, "a", encoding="utf-8"))
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    logger.addHandler(handler)


add_log_file(sys.stdout)
add_log_file(f"{WORKDIR}/log/lastest.log")
logger.setLevel(logging.INFO)


__all__ = [
    'logger',
]