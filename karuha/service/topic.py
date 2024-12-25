from typing import Any, Dict, Iterable, Optional, Union

from tinode_grpc import pb

from ..exception import KaruhaRuntimeError

from ..bot import Bot
from ..event.bot import SubscribeEvent
from ..data.topic import BaseTopic, get_topic
from ..data.types import ClientDescType
from ..data.model import ClientDesc, DefaultAccess
from ..utils.decode import dict2msg
from ..utils.event_catcher import EventCatcher
from .info import _BaseInfoService


class TopicService(_BaseInfoService[BaseTopic]):
    __slots__ = []

    async def new_topic(
        self,
        *,
        is_chan: bool = False,
        fn: Optional[str] = None,
        default_acs: Optional[DefaultAccess] = None,
        public: Optional[Dict[str, Any]] = None,
        trusted: Optional[Dict[str, Any]] = None,
        private: Optional[Dict[str, Any]] = None,
        desc: Optional[ClientDescType] = None,
        tags: Iterable[str] = (),
    ) -> str:
        if any((fn, default_acs, public, trusted, private)):
            if desc is not None:
                raise ValueError("cannot specify desc with other description fields")
            desc = ClientDesc(
                default_acs=default_acs,
                public=public,
                trusted=trusted,
                private=private,
            )
            if fn is not None:
                if desc.public is None:
                    desc.public = {}
                desc.public["fn"] = fn
        
        # bot.subscribe do not return topic id,
        # so we need to catch the event
        with EventCatcher(SubscribeEvent) as catcher:
            tid, _ = await self.bot.subscribe(
                "nch" if is_chan else "new",
                set=pb.SetQuery(
                    desc=dict2msg(desc, pb.SetDesc) if desc is not None else desc,
                    tags=tags
                )
            )
            while True:
                ev = await catcher.catch_event()
                if ev.id == tid:
                    break
        if ev.response_message is None:
            raise KaruhaRuntimeError("no response message")
        return ev.response_message.topic

    async def get_topic(
        self,
        topic_id: str,
        *,
        skip_cache: bool = False,
        use_proxy: bool = False,
        proxy_bot: Union[str, Bot, None] = None,
    ) -> BaseTopic:
        async with self._run_proxy_bot(use_proxy, proxy_bot) as bot:
            return await get_topic(bot, topic_id, skip_cache=skip_cache)
    
    async def del_topic(self, topic: Union[str, BaseTopic], /, hard: bool = False) -> None:
        id = topic.id if isinstance(topic, BaseTopic) else topic
        await self.bot.delete("topic", topic=id, hard=hard)
