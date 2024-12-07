from datetime import datetime
from typing import List, Optional

from ..utils.decode import load_json, msg2dict

from ..bot import Bot
from .cache import get_sub, get_user_desc, try_get_sub, try_get_topic_sub, try_get_user_desc
from .meta import Access, DefaultAccess, UserDesc
from .model import BaseInfo


class BaseUser(BaseInfo, frozen=True):
    user_id: str

    @property
    def staff(self) -> bool:
        if self.trusted is None:
            return False
        return self.trusted.get("staff", False)


class User(BaseUser, frozen=True):
    state: Optional[str]
    state_at: Optional[datetime] = None
    created: datetime
    updated: datetime
    touched: Optional[datetime] = None
    defacs: Optional[DefaultAccess] = None
    acs: Optional[Access] = None


class UserSub(BaseUser, frozen=True):
    updated: datetime
    deleted: Optional[datetime] = None
    touched: Optional[datetime] = None
    read: Optional[int] = None
    recv: Optional[int] = None
    clear: Optional[int] = None
    acs: Optional[Access] = None


def try_get_user(bot: Bot, /, user_id: str = "me") -> Optional[BaseUser]:
    if user_id == bot.uid:
        user_id = "me"
    desc = try_get_user_desc(bot, user_id)
    sub = None if user_id == "me" else try_get_sub(bot, user_id)
    if isinstance(desc, UserDesc) and sub is not None:
        return User(
            user_id=bot.uid,
            public=desc.public,
            trusted=desc.trusted,
            private=sub and sub.private,
            state=desc.state,
            state_at=desc.state_at,
            created=desc.created,
            updated=desc.updated,
            touched=desc.touched,
            defacs=desc.defacs,
            acs=sub and sub.acs,
        )
    elif desc is not None:
        return BaseUser(
            user_id=bot.uid,
            public=desc.public,
            trusted=desc.trusted,
            private=sub and sub.private
        )


async def get_user(bot: Bot, /, user_id: str = "me", *, skip_cache: bool = False, skip_sub_check: bool = False) -> BaseUser:
    if user_id == bot.uid:
        user_id = "me"
    desc = await get_user_desc(bot, user_id, skip_cache=skip_cache)
    sub = await get_sub(bot, user_id, skip_sub_check=skip_sub_check)
    if sub is None:
        if isinstance(desc, UserDesc):
            return User(
                user_id=bot.uid,
                public=desc.public,
                trusted=desc.trusted,
                state=desc.state,
                state_at=desc.state_at,
                created=desc.created,
                updated=desc.updated,
                touched=desc.touched,
                defacs=desc.defacs,
            )
        else:
            return BaseUser(
                user_id=bot.uid,
                public=desc.public,
                trusted=desc.trusted,
            )
    if isinstance(desc, UserDesc):
        return User(
            user_id=user_id,
            public=desc.public,
            trusted=desc.trusted,
            private=sub.private,
            state=desc.state,
            state_at=desc.state_at,
            created=desc.created,
            updated=desc.updated,
            touched=desc.touched,
            defacs=desc.defacs,
            acs=sub.acs
        )
    else:
        return BaseUser(
            user_id=user_id,
            public=desc.public,
            trusted=desc.trusted,
            private=sub.private,
        )


def try_get_user_list(bot: Bot, /, topic: str) -> List[BaseUser]:
    if subs := try_get_topic_sub(bot, topic):
        return list(filter(None, (try_get_user(bot, user_id) for user_id, _ in subs)))
    return []


async def get_user_list(bot: Bot, /, topic: str, *, ensure_all: bool = True) -> List[BaseUser]:
    if topic == "me":
        raise ValueError("cannot get user list for 'me', use get_topic_list() instead")
    if not ensure_all:
        if subs := try_get_user_list(bot, topic):
            return subs
    _, sub_meta = await bot.get(topic, "sub")
    assert sub_meta is not None
    return [
        UserSub(
            user_id=sub.user_id,
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
