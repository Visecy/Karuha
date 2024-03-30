from datetime import datetime
from typing import List, Literal, Optional, overload

from ..bot import Bot
from .cache import get_sub, get_topic_sub, get_user_desc
from .meta import Access, DefaultAccess, Subscription, UserDesc
from .topic import BaseInfo


class BaseUser(BaseInfo, frozen=True):
    user_id: str

    @property
    def topic_id(self) -> str:
        return self.user_id

    @property
    def staff(self) -> bool:
        if self.trusted is None:
            return False
        return self.trusted.get("staff", False)
    
    async def to_user(self, bot: Bot, /) -> "User":
        return await get_user(bot, self.user_id, ensure_user=True)


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


@overload
async def get_user(bot: Bot, /, user_id: str = "me", *, ensure_user: Literal[True]) -> User: ...
@overload
async def get_user(bot: Bot, /, user_id: str = "me", *, ensure_user: bool = False) -> BaseUser: ...


async def get_user(bot: Bot, /, user_id: str = "me", *, ensure_user: bool = False) -> BaseUser:
    if user_id == bot.uid:
        user_id = "me"
    desc = await get_user_desc(bot, user_id, ensure_meta=ensure_user)
    if ensure_user:
        assert isinstance(desc, UserDesc)
    if user_id == "me":
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
    sub = await get_sub(bot, user_id, ensure_meta=False)
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


@overload
async def get_user_list(bot: Bot, /, topic: str, *, ensure_user_sub: Literal[True]) -> List[UserSub]: ...
@overload
async def get_user_list(bot: Bot, /, topic: str, *, ensure_user_sub: bool = False) -> List[BaseUser]: ...


async def get_user_list(bot: Bot, /, topic: str, *, ensure_user_sub: bool = False) -> List[BaseUser]:  # type: ignore[misc]
    assert topic != "me", "cannot get user list of myself, use `get_topic_list()` instead"
    subs = await get_topic_sub(bot, topic, ensure_meta=ensure_user_sub)
    user_list = []
    for user_id, sub in subs:
        user_desc = await get_user_desc(bot, user_id, ensure_meta=False)
        if isinstance(sub, Subscription):
            user_sub = UserSub(
                user_id=user_id,
                public=user_desc.public,
                trusted=user_desc.trusted,
                private=sub.private,
                updated=sub.updated,
                deleted=sub.deleted,
                touched=sub.touched,
                read=sub.read,
                recv=sub.recv,
                clear=sub.clear,
                acs=sub.acs
            )
        else:
            user_sub = BaseUser(
                user_id=user_id,
                public=user_desc.public,
                trusted=user_desc.trusted,
                private=sub.private,
            )
        user_list.append(user_sub)
    return user_list
