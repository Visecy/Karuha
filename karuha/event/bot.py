from typing import Any, Callable, Coroutine, Union
from typing_extensions import Self

from google.protobuf.message import Message
from tinode_grpc import pb

from .. import bot
from ..text import BaseText, Drafty
from .base import Event


class BotEvent(Event):
    __slots__ = ["bot"]

    def __init__(self, bot: "bot.Bot", /) -> None:
        self.bot = bot

    def call_handler(self, handler: Callable[[Self], Coroutine]) -> None:
        self.bot._create_task(handler(self))


# Server Event Part
# =========================

    
class ServerEvent(BotEvent):
    __slots__ = ["server_message"]

    def __init__(self, bot: "bot.Bot", message: Message) -> None:
        super().__init__(bot)
        self.server_message = message
    
    def __init_subclass__(cls, on_field: str, **kwds: Any) -> None:
        super().__init_subclass__(**kwds)
        bot.Bot.server_event_map[on_field].append(cls)
    

class DataEvent(ServerEvent, on_field="data"):
    __slots__ = []

    server_message: pb.ServerData


class CtrlEvent(ServerEvent, on_field="ctrl"):
    __slots__ = []

    server_message: pb.ServerCtrl


class MetaEvent(ServerEvent, on_field="meta"):
    __slots__ = []

    server_message: pb.ServerMeta


class PresEvent(ServerEvent, on_field="pres"):
    __slots__ = []

    server_message: pb.ServerPres


class InfoEvent(ServerEvent, on_field="info"):
    __slots__ = []

    server_message: pb.ServerInfo


# Client Event Part
# =========================


class ClientEvent(BotEvent):
    __slots__ = []


class PublishEvent(ClientEvent):
    __slots__ = ["text", "topic"]

    def __init__(self, bot: "bot.Bot", topic: str, text: Union[str, Drafty, BaseText]) -> None:
        super().__init__(bot)
        self.text = text
        self.topic = topic


class SubscribeEvent(ClientEvent):
    __slots__ = ["topic"]

    def __init__(self, bot: "bot.Bot", topic: str) -> None:
        super().__init__(bot)
        self.topic = topic


class LeaveEvent(ClientEvent):
    __slots__ = ["topic"]

    def __init__(self, bot: "bot.Bot", topic: str) -> None:
        super().__init__(bot)
        self.topic = topic
