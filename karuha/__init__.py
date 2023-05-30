"""
A simple Tinode chatbot framework
"""

from pathlib import Path


WORKDIR = Path(".bot")  # dir to storage bot data

from .version import __version__
from .config import get_config, load_config, init_config
from .bot import Bot


__all__ = [
    "get_config",
    "load_config",
    "init_config",
    "Bot"
]
