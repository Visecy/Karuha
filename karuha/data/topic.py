from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic_core import to_json
from tinode_grpc import pb
from typing_extensions import deprecated

from ..bot import Bot
from ..utils.decode import load_json, msg2dict
from .cache import (
    get_group_desc,
    get_p2p_desc,
    get_sub,
    get_user_desc,
    try_get_group_desc,
    try_get_my_sub,
    try_get_p2p_desc,
    try_get_sub,
    try_get_user_desc,
)
from .meta import Access, CommonDesc, DefaultAccess, GroupTopicDesc
from .model import BaseInfo


class BaseTopic(BaseInfo, frozen=True):
    topic: str

    @property
    def id(self) -> str:
        return self.topic

    topic_id = id


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


@deprecated("Use `UserService.set_desc` instead")
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


def try_get_p2p_topic(bot: Bot, /, topic_id: str) -> Optional[BaseTopic]:
    desc = try_get_user_desc(bot, topic_id)
    info = try_get_p2p_desc(bot, topic_id)
    sub = try_get_sub(bot, topic_id)
    if desc is None:
        return
    if isinstance(desc, CommonDesc) and info is not None and sub is not None:
        return Topic(
            topic=topic_id,
            public=desc.public,
            trusted=desc.trusted,
            private=sub.private,
            created=info.created,
            updated=info.updated,
            touched=info.touched,
            defacs=desc.defacs,
            acs=sub.acs,
            seq=info.seq,
            read=sub.read,
            recv=sub.recv,
            clear=sub.clear,
        )
    return BaseTopic(
        topic=topic_id,
        public=desc.public,
        trusted=desc.trusted,
    )


async def get_p2p_topic(bot: Bot, /, topic_id: str, *, skip_cache: bool = False) -> BaseTopic:
    desc = await get_user_desc(bot, user_id=topic_id, skip_cache=skip_cache)
    sub = await get_sub(bot, topic_id=topic_id, skip_cache=skip_cache)
    info = try_get_p2p_desc(bot, topic_id)
    if isinstance(desc, CommonDesc) and skip_cache and info is None:
        info = await get_p2p_desc(bot, topic_id, skip_cache=skip_cache)
    elif not isinstance(desc, CommonDesc) or info is None:
        return BaseTopic(
            topic=topic_id,
            public=desc.public,
            trusted=desc.trusted,
            private=sub and sub.private,
        )
    return Topic(
        topic=topic_id,
        public=desc.public,
        trusted=desc.trusted,
        private=sub and sub.private,
        created=info.created,
        updated=info.updated,
        touched=info.touched,
        seq=info.seq,
        defacs=desc.defacs,
        acs=sub and sub.acs,
        read=sub and sub.read,
        recv=sub and sub.recv,
        clear=sub and sub.clear,
    )


def try_get_group_topic(bot: Bot, /, topic_id: str) -> Optional[BaseTopic]:
    desc = try_get_group_desc(bot, topic_id)
    sub = try_get_sub(bot, topic_id)
    if isinstance(desc, GroupTopicDesc) and sub is not None:
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
    elif desc is not None:
        return BaseTopic(
            topic=topic_id,
            public=desc.public,
            trusted=desc.trusted,
            private=sub and sub.private,
        )


async def get_group_topic(bot: Bot, /, topic_id: str, *, skip_cache: bool = False) -> BaseTopic:
    desc = await get_group_desc(bot, topic_id, skip_cache=skip_cache)
    sub = await get_sub(bot, topic_id, skip_cache=skip_cache)
    if not isinstance(desc, GroupTopicDesc):
        return BaseTopic(topic=topic_id, public=desc.public, trusted=desc.trusted, private=sub and sub.private)
    return Topic(
        topic=topic_id,
        public=desc.public,
        trusted=desc.trusted,
        private=sub and sub.private,
        is_chan=desc.is_chan,
        defacs=desc.defacs,
        acs=sub and sub.acs,
        seq=desc.seq,
        created=desc.created,
        updated=desc.updated,
        touched=desc.touched,
        read=sub and sub.read,
        recv=sub and sub.recv,
        clear=sub and sub.clear,
    )


async def get_topic(bot: Bot, /, topic_id: str, *, skip_cache: bool = False) -> BaseTopic:
    if topic_id == "me":
        raise ValueError("cannot get topic info for 'me', use get_user() instead")
    if topic_id.startswith("grp"):
        return await get_group_topic(bot, topic_id, skip_cache=skip_cache)
    else:
        return await get_p2p_topic(bot, topic_id, skip_cache=skip_cache)


def try_get_topic(bot: Bot, /, topic_id: str) -> Optional[BaseTopic]:
    if topic_id.startswith("grp"):
        return try_get_group_topic(bot, topic_id)
    else:
        return try_get_p2p_topic(bot, topic_id)


def try_get_topic_list(bot: Bot, /) -> List[BaseTopic]:
    if subs := try_get_my_sub(bot):
        return list(filter(None, (try_get_topic(bot, topic) for topic, _ in subs)))
    return []


async def get_topic_list(bot: Bot, /, *, ensure_all: bool = True) -> List[BaseTopic]:  # type: ignore[misc]
    if not ensure_all:
        if subs := try_get_topic_list(bot):
            return subs
    _, sub_meta = await bot.get("me", "sub")
    assert sub_meta is not None
    return [
        TopicSub(
            topic=sub.topic,
            public=load_json(sub.public),
            trusted=load_json(sub.trusted),
            private=load_json(sub.private),
            updated=sub.updated_at,  # type: ignore
            touched=sub.touched_at,  # type: ignore
            deleted=sub.deleted_at,  # type: ignore
            read=sub.read_id,
            recv=sub.recv_id,
            clear=sub.del_id,
            acs=msg2dict(sub.acs),  # type: ignore
        )
        for sub in sub_meta.sub
    ]
