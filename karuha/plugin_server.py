import asyncio
from concurrent import futures
from typing import Any, Awaitable, Callable, Coroutine, Mapping, Sequence, Union
from typing_extensions import Self

import grpc
from tinode_grpc import pb, pbx

from .event import Event
from .logger import logger


class PluginServerEvent(Event):
    """base class for all event from plugin server"""
    __slots__ = ["raw_message"]

    def __init__(self, message: Union[pb.TopicEvent, pb.AccountEvent, pb.SubscriptionEvent, pb.MessageEvent]) -> None:
        super().__init__()
        self.raw_message = message

    @property
    def action(self) -> pb.Crud:
        return self.raw_message.action

    def call_handler(self, handler: Callable[[Self], Coroutine]) -> Awaitable:
        loop = asyncio.get_running_loop()
        future = asyncio.run_coroutine_threadsafe(handler(self), loop)
        return asyncio.wrap_future(future, loop=loop)
    
    def __init_subclass__(cls, property_export: Union[Sequence[str], Mapping[str, str], None] = None, **kwds: Any) -> None:
        super().__init_subclass__(**kwds)
        if isinstance(property_export, Sequence):
            property_export = {i: i for i in property_export}
        if property_export:
            for k, v in property_export.items():
                setattr(cls, k, property(lambda e: getattr(e.raw_message, v)))


class TopicEvent(PluginServerEvent, property_export={"name": "name", "topic": "desc"}):
    __slots__ = []

    raw_message: pb.TopicEvent
    name: str
    topic: pb.TopicDesc


class AccountEvent(PluginServerEvent, property_export=["user_id"]):
    __slots__ = []

    raw_message: pb.AccountEvent
    user_id: str


class SubscriptionEvent(PluginServerEvent, property_export=["topic", "user_id"]):
    __slots__ = []

    raw_message: pb.SubscriptionEvent
    user_id: str
    topic: str


class MessageEvent(PluginServerEvent, property_export={"data": "msg"}):
    __slots__ = []

    raw_message: pb.MessageEvent
    data: pb.ServerData

    @property
    def topic(self) -> str:
        return self.data.topic
    
    @property
    def user_id(self) -> str:
        return self.data.from_user_id
    
    @property
    def content(self) -> bytes:
        return self.data.content


class Plugin(pbx.PluginServicer):
    def Topic(self, tpc_event: pb.TopicEvent, context: grpc.ServicerContext):
        TopicEvent(tpc_event).trigger()
        return pb.Unused()
    
    def Account(self, acc_event: pb.AccountEvent, context: grpc.ServicerContext):
        AccountEvent(acc_event).trigger()
        return pb.Unused()
    
    def Subscription(self, tpc_event: pb.TopicEvent, context: grpc.ServicerContext):
        TopicEvent(tpc_event).trigger()
        return pb.Unused()


def init_server(address: str) -> grpc.Server:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    pbx.add_PluginServicer_to_server(Plugin(), server)
    server.add_insecure_port(address)
    logger.info(f"plugin server starts at {address}")
    return server
