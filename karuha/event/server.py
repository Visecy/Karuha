import asyncio
from collections import defaultdict
from typing import Callable, Coroutine, List, Type
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
    
    async def default_handler(self) -> None:
        pass
    
    def trigger(self, task_creator: Callable[[Coroutine], asyncio.Task] = asyncio.create_task) -> None:
        task_creator(self.default_handler())
        return super().trigger(task_creator)

    def __init_subclass__(cls, on_field: str) -> None:
        super().__init_subclass__()
        _server_event[on_field].append(cls)
    

class DataEvent(ServerEvent, on_field="data"):
    __slots__ = []

    raw_message: pb.ServerData

    async def default_handler(self) -> None:
        msg = self.raw_message
        self.bot.logger.info(f"({msg.topic})=> {msg.content.decode()}")
        await self.bot.note_read(msg.topic, msg.seq_id)


class CtrlEvent(ServerEvent, on_field="ctrl"):
    __slots__ = []

    raw_message: pb.ServerCtrl

    async def default_handler(self) -> None:
        tid = self.raw_message.id
        if tid in self.bot._wait_list:
            self.bot._wait_list[tid].set_result(self.raw_message)


class MetaEvent(ServerEvent, on_field="meta"):
    __slots__ = []

    raw_message: pb.ServerMeta


class PresEvent(ServerEvent, on_field="pres"):
    __slots__ = []

    raw_message: pb.ServerPres

    async def default_handler(self) -> None:
        msg = self.raw_message
        if msg.topic != "me":
            return
        if msg.what in [pb.ServerPres.ON, pb.ServerPres.MSG]:
            await self.bot.subscribe(msg.src)
        elif msg.what == pb.ServerPres.OFF:
            await self.bot.leave(msg.src)


class InfoEvent(ServerEvent, on_field="info"):
    __slots__ = []

    raw_message: pb.ServerInfo


def _get_server_event(field_name: str) -> List[Type[ServerEvent]]:
    return _server_event[field_name]
