from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel

from ..bot import Bot

from .cache import get_sub, get_topic_sub, get_user_desc
from .meta import Access, DefaultAccess, UserDesc


class BaseUser(BaseModel, frozen=True):
    user_id: str
    public: Optional[Dict[str, Any]] = None
    trusted: Optional[Dict[str, Any]] = None
    private: Optional[Dict[str, Any]] = None


class User(BaseUser, frozen=True):
    state: Optional[str]
    state_at: Optional[datetime]
    created: datetime
    updated: datetime
    touched: Optional[datetime]
    defacs: Optional[DefaultAccess] = None
    acs: Optional[Access] = None


async def get_user(bot: Bot, /, user_id: str, *, ensure_user: bool = False) -> BaseUser:
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
