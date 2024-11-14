"""
A simple Tinode chatbot framework
"""
import os
from pathlib import Path


WORKDIR = Path(os.environ.get("KARUHA_HOME", ".bot"))  # dir to storage bot data


from .version import __version__
from .config import get_config, load_config, init_config, save_config, reset_config, Config
from .config import Server as ServerConfig, Bot as BotConfig
from .bot import Bot, BotState
from .exception import KaruhaException
from .event import on, on_event, Event
from .text import Drafty, BaseText, PlainText, Message, TextChain
from .command import CommandCollection, AbstractCommand, AbstractCommandParser, BaseSession, MessageSession, CommandSession, get_collection, on_command, rule, on_rule
from .data import get_user, get_topic, try_get_user, try_get_topic
from .runner import try_get_bot, get_bot, add_bot, try_add_bot, get_all_bots, remove_bot, cancel_all_bots, async_run, run, reset


__all__ = [
    # runner
    "add_bot",
    "try_add_bot",
    "get_bot",
    "try_get_bot",
    "get_all_bots",
    "remove_bot",
    "cancel_all_bots",
    "async_run",
    "run",
    "reset",
    # bot
    "Bot",
    "BotState",
    # config
    "get_config",
    "init_config",
    "load_config",
    "save_config",
    "reset_config",
    "Config",
    "BotConfig",
    "ServerConfig",
    # event
    "Event",
    # text
    "Drafty",
    "BaseText",
    "PlainText",
    "Message",
    "TextChain",
    # command
    "CommandCollection",
    "AbstractCommand",
    "AbstractCommandParser",
    "get_collection",
    "BaseSession",
    "MessageSession",
    "CommandSession",
    "rule",
    # data
    "get_user",
    "get_topic",
    "try_get_user",
    "try_get_topic",
    # decorator
    "on",
    "on_event",
    "on_command",
    "on_rule",
    # exception
    "KaruhaException"
]
