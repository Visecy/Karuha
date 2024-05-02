import asyncio
from functools import partial
from typing import Awaitable, Callable, Coroutine, Union

from tinode_grpc import pb
from typing_extensions import Self

from ..command.session import BaseSession

from ..bot import Bot
from ..logger import logger
from ..utils.proxy_propery import ProxyProperty
from . import on
from .base import Event
from .bot import BotEvent
from ..runner import get_all_bots, _get_running_loop


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
        loop = _get_running_loop()
        future = asyncio.run_coroutine_threadsafe(handler(self), loop)
        return asyncio.wrap_future(future, loop=loop)


PluginServerProperty = partial(ProxyProperty, "raw_message")


class TopicEvent(PluginServerEvent):
    __slots__ = []

    raw_message: pb.TopicEvent
    
    name: ProxyProperty[str] = PluginServerProperty()
    desc: ProxyProperty["pb.TopicDesc"] = PluginServerProperty()


class AccountEvent(PluginServerEvent):
    __slots__ = []

    raw_message: pb.AccountEvent

    user_id: ProxyProperty[str] = PluginServerProperty()
    action: ProxyProperty["pb.Crud"] = PluginServerProperty()
    public: ProxyProperty[bytes] = PluginServerProperty()

    async def __default_handler__(self) -> None:
        action = self.action
        if action == pb.Crud.CREATE:
            for i in get_all_bots():
                if not i.config.auto_subscribe_new_user:
                    logger.debug(f"ignore auto subscribe for {i.name}")
                    continue
                await i.subscribe(self.user_id)
                AccountCreateEvent.new(i, self.raw_message)


class SubscriptionEvent(PluginServerEvent):
    __slots__ = []

    raw_message: pb.SubscriptionEvent

    user_id: ProxyProperty[str] = PluginServerProperty()
    topic: ProxyProperty[str] = PluginServerProperty()


class MessageEvent(PluginServerEvent, property_export={"data": "msg"}):
    __slots__ = []

    raw_message: pb.MessageEvent

    data: ProxyProperty["pb.ServerData"] = PluginServerProperty(name="msg")
    topic = ProxyProperty[str]("data")
    from_user_id = ProxyProperty[str]("data")
    user_id = ProxyProperty[str]("data", name="from_user_id")
    content = ProxyProperty[bytes]("data")


class AccountCreateEvent(BotEvent):
    __slots__ = ["raw_message"]

    raw_message: pb.AccountEvent

    user_id: ProxyProperty[str] = PluginServerProperty()
    action: ProxyProperty["pb.Crud"] = PluginServerProperty()
    public: ProxyProperty[bytes] = PluginServerProperty()

    def __init__(self, bot: Bot, message: pb.AccountEvent) -> None:
        super().__init__(bot)
        self.raw_message = message
    
    def get_session(self) -> BaseSession:
        return BaseSession(self.bot, self.user_id)


on_new_account = on(AccountCreateEvent)
