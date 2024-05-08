from abc import abstractproperty
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, overload

from pydantic import BaseModel
from pydantic_core import to_json
from tinode_grpc import pb

from ..bot import Bot
from .meta import Access, CommonDesc, DefaultAccess, GroupTopicDesc, Subscription
from .cache import get_my_sub, p2p_cache, get_group_desc, get_p2p_desc, get_sub, get_user_desc, try_get_p2p_desc, try_get_group_desc


class BaseInfo(BaseModel, frozen=True):
    public: Optional[Dict[str, Any]] = None
    trusted: Optional[Dict[str, Any]] = None
    private: Optional[Dict[str, Any]] = None

    @property
    def fn(self) -> Optional[str]:
        if self.public:
            return self.public.get("fn")

    @property
    def note(self) -> Optional[str]:
        if self.public:
            return self.public.get("note")

    @property
    def comment(self) -> Optional[str]:
        if self.private:
            return self.private.get("comment")

    @property
    def verified(self) -> bool:
        if self.trusted is None:
            return False
        return self.trusted.get("verified", False)
    
    @abstractproperty
    def topic_id(self) -> str:
        raise NotImplementedError

    async def set_info(
        self,
        bot: Bot,
        /,
        public: Optional[Dict[str, Any]] = None,
        trusted: Optional[Dict[str, Any]] = None,
        private: Optional[Dict[str, Any]] = None,
        *,
        update: bool = False,
    ) -> None:
        if update:
            if public is not None and self.public is not None:
                public = public.copy().update(self.public)
            if trusted is not None and self.trusted is not None:
                trusted = trusted.copy().update(self.trusted)
            if private is not None and self.private is not None:
                private = private.copy().update(self.private)
        await set_info(
            bot, self.topic_id, public=public, trusted=trusted, private=private
        )

    async def set_public(self, bot: Bot, /, public: Optional[Dict[str, Any]] = None, *, update: bool = False) -> None:
        await self.set_info(bot, public=public, update=update)

    async def set_trusted(self, bot: Bot, /, trusted: Optional[Dict[str, Any]] = None, *, update: bool = False) -> None:
        await self.set_info(bot, trusted=trusted, update=update)

    async def set_private(self, bot: Bot, /, private: Optional[Dict[str, Any]] = None, *, update: bool = False) -> None:
        await self.set_info(bot, private=private, update=update)

    async def set_fn(self, bot: Bot, /, fn: str) -> None:
        await self.set_info(bot, public={"fn": fn}, update=True)

    async def set_note(self, bot: Bot, /, note: str) -> None:
        await self.set_info(bot, public={"note": note}, update=True)

    async def set_comment(self, bot: Bot, /, comment: str) -> None:
        await self.set_info(bot, private={"comment": comment}, update=True)


class BaseTopic(BaseInfo, frozen=True):
    topic: str

    @property
    def topic_id(self) -> str:
        return self.topic
    
    async def ensure_topic(self, bot: Bot, /) -> "Topic":
        return await get_topic(bot, self.topic, ensure_topic=True)


class Topic(BaseTopic, frozen=True):
    created: datetime
    updated: datetime
    touched: Optional[datetime]
    defacs: Optional[DefaultAccess] = None
    acs: Optional[Access] = None
    seq: Optional[int] = None
    read: Optional[int] = None
    recv: Optional[int] = None
    clear: Optional[int] = None
    is_chan: bool = False

    async def ensure_topic(self, bot: Bot) -> "Topic":
        return self


class TopicSub(BaseTopic, frozen=True):
    updated: datetime
    deleted: Optional[datetime] = None
    touched: Optional[datetime] = None
    read: Optional[int] = None
    recv: Optional[int] = None
    clear: Optional[int] = None
    acs: Optional[Access] = None


async def set_info(
    bot: Bot,
    /,
    topic_id: str,
    *,
    public: Optional[Dict[str, Any]] = None,
    trusted: Optional[Dict[str, Any]] = None,
    private: Optional[Dict[str, Any]] = None,
) -> None:
    set_desc = pb.SetDesc(
        public=to_json(public) if public else None,
        trusted=to_json(trusted) if trusted else None,
        private=to_json(private) if private else None,
    )
    if topic_id == bot.uid:
        topic_id = "me"
    if not topic_id.startswith("usr") or (public is None and trusted is None):
        await bot.set(topic_id, desc=set_desc)
        return
    extra = pb.ClientExtra(on_behalf_of=topic_id)
    await bot.subscribe("me", set=pb.SetQuery(desc=set_desc), extra=extra)
    await bot.leave("me", extra=extra)


def try_get_p2p_topic(bot: Bot, /, topic_id: str) -> Optional[TopicSub]:
    desc = try_get_p2p_desc(bot, topic_id)
    if desc is not None:
        return BaseTopic(
            topic=topic_id,
            public=desc.public,
            trusted=desc.trusted,
        )


@overload
async def get_p2p_topic(bot: Bot, /, topic_id: str, *, ensure_topic: Literal[True]) -> Topic: ...
@overload
async def get_p2p_topic(bot: Bot, /, topic_id: str, *, ensure_topic: bool = False) -> BaseTopic: ...


async def get_p2p_topic(bot: Bot, /, topic_id: str, *, ensure_topic: bool = False) -> BaseTopic:
    user_desc = await get_user_desc(bot, user_id=topic_id, ensure_meta=False)
    sub = await get_sub(bot, topic_id=topic_id, ensure_meta=False)
    if (
        not isinstance(user_desc, CommonDesc)
        or (not ensure_topic and frozenset((topic_id, bot.uid)) not in p2p_cache)
    ):
        return BaseTopic(
            topic=topic_id,
            public=user_desc.public,
            trusted=user_desc.trusted,
            private=sub.private,
        )
    p2p_desc = await get_p2p_desc(bot, user_id=topic_id)
    return Topic(
        topic=topic_id,
        public=user_desc.public,
        trusted=user_desc.trusted,
        private=sub.private,
        created=p2p_desc.created,
        updated=p2p_desc.updated,
        touched=p2p_desc.touched,
        seq=p2p_desc.seq,
        defacs=user_desc.defacs,
        acs=sub.acs,
        read=sub.read,
        recv=sub.recv,
        clear=sub.clear
    )


@overload
async def get_group_topic(bot: Bot, /, topic_id: str, *, ensure_topic: Literal[True]) -> Topic: ...
@overload
async def get_group_topic(bot: Bot, /, topic_id: str, *, ensure_topic: bool = False) -> BaseTopic: ...


async def get_group_topic(bot: Bot, /, topic_id: str, *, ensure_topic: bool = False) -> BaseTopic:
    desc = await get_group_desc(bot, topic_id, ensure_meta=ensure_topic)
    sub = await get_sub(bot, topic_id, ensure_meta=False)
    if not isinstance(desc, GroupTopicDesc):
        return BaseTopic(
            topic=topic_id,
            public=desc.public,
            trusted=desc.trusted,
            private=sub.private
        )
    return Topic(
        topic=topic_id,
        public=desc.public,
        trusted=desc.trusted,
        private=sub.private,
        is_chan=desc.is_chan,
        defacs=desc.defacs,
        acs=sub.acs,
        seq=desc.seq,
        created=desc.created,
        updated=desc.updated,
        touched=desc.touched,
        read=sub.read,
        recv=sub.recv,
        clear=sub.clear,
    )


@overload
async def get_topic(bot: Bot, topic_id: str, /, *, ensure_topic: Literal[True]) -> Topic: ...
@overload
async def get_topic(bot: Bot, topic_id: str, /, *, ensure_topic: bool = False) -> BaseTopic: ...


async def get_topic(bot: Bot, /, topic_id: str, *, ensure_topic: bool = False) -> BaseTopic:
    if topic_id.startswith("grp"):
        return await get_group_topic(bot, topic_id, ensure_topic=ensure_topic)
    else:
        return await get_p2p_topic(bot, topic_id, ensure_topic=ensure_topic)


@overload
async def get_topic_list(bot: Bot, /, *, ensure_topic_sub: Literal[True]) -> List[TopicSub]: ...
@overload
async def get_topic_list(bot: Bot, /, *, ensure_topic_sub: bool = False) -> List[BaseTopic]: ...


async def get_topic_list(bot: Bot, /, *, ensure_topic_sub: bool = False) -> List[BaseTopic]:  # type: ignore[misc]
    subs = await get_my_sub(bot, ensure_meta=ensure_topic_sub)
    topic_list = []
    for topic_id, sub in subs:
        topic = await get_topic(bot, topic_id, ensure_topic=False)
        if isinstance(sub, Subscription):
            topic_sub = TopicSub(
                topic=topic_id,
                public=topic.public,
                trusted=topic.trusted,
                private=topic.private,
                updated=sub.updated,
                deleted=sub.deleted,
                touched=sub.touched,
                read=sub.read,
                recv=sub.recv,
                clear=sub.clear,
                acs=sub.acs,
            )
        else:
            topic_sub = topic
        topic_list.append(topic_sub)
    return topic_list
