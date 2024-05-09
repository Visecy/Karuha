"""
Text message processing module.

Provides a text representation and a converter between the two that are easier to read and use than Drafty.
"""

from .drafty import Drafty, DraftyFormat, DraftyExtend
from .textchain import *
from .convert import drafty2tree, tree2text, drafty2text, eval_spans, to_span_tree
from .message import Message, MessageSession, Head


DraftyMessage = Drafty


__all__ = [
    # drafty
    "Drafty",
    "DraftyMessage",
    "DraftyFormat",
    "DraftyExtend",
    # text
    "BaseText",
    "PlainText",
    "InlineCode",
    "TextChain",
    "Bold",
    "Italic",
    "Strikethrough",
    "Highlight",
    "Hidden",
    "Row",
    "Form",
    "Link",
    "Mention",
    "Hashtag",
    "Button",
    "VideoCall",
    "File",
    "Image",
    "Audio",
    "Video",
    # converter
    "drafty2tree",
    "tree2text",
    "drafty2text",
    # message
    "Message",
    "MessageSession",
    "Head",
]
