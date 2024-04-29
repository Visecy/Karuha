import asyncio
from typing import Any, List, Optional, Union, overload
from weakref import WeakSet

from tinode_grpc import pb

from ..bot import Bot

from ..event.message import MessageDispatcher
from ..text.message import Message


@overload
async def get_data(bot: Bot, topic_id: str, *, seq_id: Optional[int] = None) -> Message: ...
@overload
async def get_data(bot: Bot, topic_id: str, *, low: Optional[int] = None, hi: Optional[int] = None) -> List[Message]: ...


async def get_data(bot: Bot, topic_id: str, *, seq_id: Optional[int] = None, low: Optional[int] = None, hi: Optional[int] = None) -> Union[List[Message], Message]:
    if low is None or hi is None:
        assert seq_id is not None, "seq_id or low and hi must be specified"
        low = hi = seq_id
    with DataDispatcher(topic_id, low, hi) as dispatcher:
        await bot.get_query(topic_id, "data", data=pb.GetOpts(since_id=low, before_id=hi + 1))
        messages = await dispatcher.wait()
    if seq_id is not None:
        assert len(messages) == 1, "seq_id must be in range"
        return messages[0]
    return messages


class DataDispatcher(MessageDispatcher):
    __slots__ = ["topic", "hi", "low", "data", "_futures"]

    def __init__(self, topic: str, /, low: int, hi: int) -> None:
        super().__init__(once=False)
        self.topic = topic
        self.hi = hi
        self.low = low
        self.data = {}
        self._futures = WeakSet()
    
    def match(self, message: Message, /) -> float:
        if message.topic == self.topic and self.low <= message.seq_id <= self.hi:
            return 3.0
        return 0
    
    def run(self, message: Message) -> Any:
        self.data[message.seq_id] = message
        if len(self.data) >= self.hi - self.low + 1:
            for future in self._futures:
                if future.done():
                    continue
                future.set_result(None)
            self.deactivate()
    
    async def wait(self) -> List[Message]:
        if len(self.data) < self.hi - self.low + 1:
            future = asyncio.Future()
            self._futures.add(future)
            await future
        return list(self.data.values())