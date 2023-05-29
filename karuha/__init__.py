"""
A simple Tinode chatbot framework
"""

WORKDIR = ".bot"  # dir to storage bot data

from .version import __version__
from .logger import logger
from .config import get_config, load_config, init_config
from .bot import Bot
