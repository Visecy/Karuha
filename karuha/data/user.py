from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, overload

from ..bot import Bot
from .cache import get_my_sub, get_sub, get_user_desc
from .meta import Access, DefaultAccess, UserDesc
from .topic import BaseInfo, set_info


class BaseUser(BaseInfo, frozen=True):
    user_id: str
    
    async def set_info(self, bot: Bot, /, public: Optional[Dict[str, Any]] = None, trusted: Optional[Dict[str, Any]] = None, private: Optional[Dict[str, Any]] = None, *, update: bool = False) -> None:
        if update:
            if public is not None and self.public is not None:
                public = public.copy().update(self.public)
            if trusted is not None and self.trusted is not None:
                trusted = trusted.copy().update(self.trusted)
            if private is not None and self.private is not None:
                private = private.copy().update(self.private)
        await set_info(bot, self.user_id, public=public, trusted=trusted, private=private)

    @property
    def verified(self) -> bool:
        if self.trusted is None:
            return False
        return self.trusted.get("verified", False)
    
    @property
    def staff(self) -> bool:
        if self.trusted is None:
            return False
        return self.trusted.get("staff", False)


class User(BaseUser, frozen=True):
    state: Optional[str]
    state_at: Optional[datetime]
    created: datetime
    updated: datetime
    touched: Optional[datetime]
    defacs: Optional[DefaultAccess] = None
    acs: Optional[Access] = None


@overload
async def get_user(bot: Bot, /, user_id: str = "me", *, ensure_user: Literal[False] = False) -> BaseUser: ...
@overload
async def get_user(bot: Bot, /, user_id: str = "me", *, ensure_user: Literal[True]) -> User: ...

async def get_user(bot: Bot, /, user_id: str = "me", *, ensure_user: bool = False) -> BaseUser:
    desc = await get_user_desc(bot, user_id, ensure_meta=ensure_user)
    if ensure_user:
        assert isinstance(desc, UserDesc)
    if user_id == "me" or user_id == bot.uid:
        if isinstance(desc, UserDesc):
            return User(
                user_id=user_id,
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
                user_id=user_id,
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
async def get_user_list(bot: Bot, /, *, ensure_user: Literal[False] = False) -> List[BaseUser]: ...
@overload
async def get_user_list(bot: Bot, /, *, ensure_user: Literal[True]) -> List[User]: ...

async def get_user_list(bot: Bot, /, *, ensure_user: bool = False) -> List[BaseUser]:  # type: ignore[misc]
    subs = await get_my_sub(bot)
    user_list = []
    for topic_id, _ in subs:
        if not topic_id.startswith("usr"):
            continue
        user_list.append(await get_user(bot, topic_id, ensure_user=ensure_user))  # type: ignore[misc]
    return user_list
