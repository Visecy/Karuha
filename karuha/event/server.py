from google.protobuf.message import Message
from tinode_grpc import pb

from .. import bot
from .base import BaseEvent
from .client import SubscribeEvent, LeaveEvent


class ServerEvent(BaseEvent):
    __slots__ = ["server_message"]

    def __init__(self, bot: "bot.Bot", message: Message) -> None:
        super().__init__(bot)
        self.server_message = message
    
    async def default_handler(self) -> None:
        pass
    
    def trigger(self) -> None:
        self.bot._create_task(self.default_handler())
        return super().trigger()

    def __init_subclass__(cls, on_field: str) -> None:
        super().__init_subclass__()
        bot.Bot.server_event_map[on_field].append(cls)
    

class DataEvent(ServerEvent, on_field="data"):
    __slots__ = []

    server_message: pb.ServerData

    async def default_handler(self) -> None:
        msg = self.server_message
        self.bot.logger.info(f"({msg.topic})=> {msg.content.decode()}")
        await self.bot.note_read(msg.topic, msg.seq_id)


class CtrlEvent(ServerEvent, on_field="ctrl"):
    __slots__ = []

    server_message: pb.ServerCtrl

    async def default_handler(self) -> None:
        tid = self.server_message.id
        if tid in self.bot._wait_list:
            self.bot._wait_list[tid].set_result(self.server_message)


class MetaEvent(ServerEvent, on_field="meta"):
    __slots__ = []

    server_message: pb.ServerMeta


class PresEvent(ServerEvent, on_field="pres"):
    __slots__ = []

    server_message: pb.ServerPres

    async def default_handler(self) -> None:
        msg = self.server_message
        if msg.topic != "me":
            return
        if msg.what in [pb.ServerPres.ON, pb.ServerPres.MSG]:
            SubscribeEvent(self.bot, msg.src).trigger()
        elif msg.what == pb.ServerPres.OFF:
            LeaveEvent(self.bot, msg.src).trigger()


class InfoEvent(ServerEvent, on_field="info"):
    __slots__ = []

    server_message: pb.ServerInfo
