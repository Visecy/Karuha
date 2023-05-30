from collections import defaultdict
from typing import List, Type
from google.protobuf.message import Message
from tinode_grpc import pb

from .. import bot
from .base import BaseEvent


_server_event = defaultdict(list)


class ServerEvent(BaseEvent):
    __slots__ = ["raw_message"]

    def __init__(self, bot: "bot.Bot", message: Message) -> None:
        super().__init__(bot)
        self.raw_message = message

    def __init_subclass__(cls, on_field: str) -> None:
        super().__init_subclass__()
        _server_event[on_field].append(cls)
    

class DataEvent(ServerEvent, on_field="data"):
    __slots__ = []

    raw_message: pb.ServerData

    async def __call__(self) -> None:
        ...


class CtrlEvent(ServerEvent, on_field="ctrl"):
    __slots__ = []

    raw_message: pb.ServerCtrl

    async def __call__(self) -> None:
        tid = self.raw_message.id
        if tid in self.bot._wait_list:
            self.bot._wait_list[tid].set_result(self.raw_message)


class MetaEvent(ServerEvent, on_field="meta"):
    __slots__ = []

    raw_message: pb.ServerMeta

    async def __call__(self) -> None:
        ...


class PresEvent(ServerEvent, on_field="pres"):
    __slots__ = []

    raw_message: pb.ServerPres

    async def __call__(self) -> None:
        ...

class InfoEvent(ServerEvent, on_field="info"):
    __slots__ = []

    raw_message: pb.ServerInfo
    
    async def __call__(self) -> None:
        ...


def _get_server_event(field_name: str) -> List[Type[ServerEvent]]:
    return _server_event[field_name]
