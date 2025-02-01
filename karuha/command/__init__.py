from .rule import *  # noqa: F403
from .command import AbstractCommand, FunctionCommand
from .collection import (
    CommandCollection,
    add_sub_collection,
    get_collection,
    new_collection,
    remove_sub_collection,
    reset_collection,
    set_collection,
    set_collection_factory,
    set_prefix,
)
from .decoractor import on_command, on_rule
from .parser import AbstractCommandParser, SimpleCommandParser

from ..event.command import (
    BaseCommandEvent,
    CommandCompleteEvent,
    CommandEvent,
    CommandFailEvent,
    CommandNotFoundEvent,
    CommandPrepareEvent,
)


__all__ = [
    # command
    "AbstractCommand",
    "FunctionCommand",
    # parser
    "AbstractCommandParser",
    "SimpleCommandParser",
    # rule
    "BaseRule",
    "KeywordRule",
    "MentionMeRule",
    "MentionRule",
    "NotRule",
    "OrRule",
    "RegexRule",
    "SeqIDRule",
    "TopicRule",
    "UserIDRule",
    "AndRule",
    "QuoteRule",
    "ToMeRule",
    "NoopRule",
    "rule",
    # collection
    "CommandCollection",
    "get_collection",
    "new_collection",
    "add_sub_collection",
    "remove_sub_collection",
    "reset_collection",
    "set_collection",
    "set_collection_factory",
    "set_prefix",
    # event
    "BaseCommandEvent",
    "CommandEvent",
    "CommandFailEvent",
    "CommandNotFoundEvent",
    "CommandPrepareEvent",
    "CommandCompleteEvent",
    # decorator
    "on_command",
    "on_rule",
]
