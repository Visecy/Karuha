"""
A simple Tinode chatbot framework
"""

WORKDIR = ".bot"  # dir to storage bot data

from .logger import logger
from .config import get_config, load_config
