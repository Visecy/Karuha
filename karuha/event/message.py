from asyncio import iscoroutine
from functools import partial
from typing import Dict, Union

from typing_extensions import Self

from ..bot import Bot, decode_mapping
from ..text import BaseText, Drafty
from ..text.message import Message
from ..utils.dispatcher import AbstractDispatcher
from ..utils.locks import Lock
from ..utils.proxy_propery import ProxyProperty
from . import on
from .bot import BotEvent, DataEvent, ensure_text_len


MessageProperty = partial(ProxyProperty, "message", mutable=True)


class MessageEvent(BotEvent):
    """a parsed DataMessage"""

    __slots__ = ["message"]

    def __init__(self, bot: Bot, /, topic: str, user_id: str, seq_id: int, head: Dict[str, str], content: bytes) -> None:
        super().__init__(bot)
        self.message = Message.new(bot, topic, user_id, seq_id, head, content)

    @classmethod
    def from_data_event(cls, event: DataEvent, /) -> Self:
        message = event.server_message
        return cls(
            event.bot, message.topic, message.from_user_id, message.seq_id, decode_mapping(message.head), message.content
        )

    async def __default_handler__(self) -> None:
        async with get_message_lock():
            result = MessageDispatcher.dispatch(self.dump())
        if iscoroutine(result):
            await result

    def dump(self) -> Message:
        return self.message

    topic: ProxyProperty[str] = MessageProperty()
    user_id: ProxyProperty[str] = MessageProperty()
    seq_id: ProxyProperty[int] = MessageProperty()
    content: ProxyProperty[bytes] = MessageProperty()
    raw_text: ProxyProperty[Union[str, Drafty]] = MessageProperty()
    text: ProxyProperty[Union[str, BaseText]] = MessageProperty()


@DataEvent.add_handler
async def _(event: DataEvent) -> None:
    event.bot.logger.info(f"({event.topic})=> {ensure_text_len(event.text)}")
    MessageEvent.from_data_event(event).trigger(return_exceptions=True)
    await event.bot.note_read(event.topic, event.seq_id)


class MessageDispatcher(AbstractDispatcher[Message]):
    __slots__ = []

    dispatchers = set()


def get_message_lock() -> Lock:
    return MessageEvent.get_lock()


def reset_message_lock() -> None:
    del MessageEvent.__event_lock__


on_message = on(MessageEvent)
