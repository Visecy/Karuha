from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Iterable, Mapping, Optional, Tuple, Union

from pydantic_core import to_json
from tinode_grpc import pb
from google.protobuf.json_format import ParseDict
from pydantic import BaseModel

from .base import BaseService
from ..runner import add_bot, run_bot
from ..data.user import BaseUser, get_user
from ..data.types import ClientCredType, UserStateType
from ..bot import Bot, ProxyBot


def _parse_cred(cred: ClientCredType) -> pb.ClientCred:
    if isinstance(cred, pb.ClientCred):
        return cred
    elif isinstance(cred, BaseModel):
        return ParseDict(cred.model_dump(), pb.ClientCred())
    return ParseDict(cred, pb.ClientCred())


class UserService(BaseService):
    __slots__ = []

    async def new_bot(
        self,
        uname: str,
        password: str,
        *,
        name: Optional[str] = None,
        tags: Iterable[str] = (),
        cred: Iterable[ClientCredType],
        state: UserStateType = "ok",
        use_proxy: bool = False,
        start_run: bool = True,
    ) -> Bot:
        secret = f"{uname}:{password}"
        _, params = await self.bot.account(
            "new",
            "basic",
            secret.encode(),
            do_login=False,
            state=state,
            tags=tags,
            cred=map(_parse_cred, cred),
        )
        user_id = params["user"]
        if name is None:
            name = f"{uname}_{user_id}"
        if not use_proxy:
            bot = Bot(name, schema="basic", secret=secret, server=self.bot.server)
        else:
            bot = ProxyBot.from_bot(self.bot, user_id, name)
        if start_run:
            add_bot(bot)
        return bot

    async def new_user(
        self,
        uname: str,
        password: str,
        *,
        tags: Iterable[str] = (),
        cred: Iterable[ClientCredType] = (),
        state: Optional[UserStateType] = None
    ) -> Tuple[str, str]:
        secret = f"{uname}:{password}"
        _, params = await self.bot.account(
            "new",
            "basic",
            secret.encode(),
            do_login=False,
            state=state,
            tags=tags,
            cred=map(_parse_cred, cred),
        )
        user_id = params["user"]
        token = params["token"]
        return user_id, token

    async def get_user(
        self,
        user_id: str,
        *,
        skip_cache: bool = False,
        skip_sub_check: bool = False,
        use_proxy: bool = False,
    ) -> BaseUser:
        if not use_proxy:
            return await get_user(
                self.bot, user_id, skip_cache=skip_cache, skip_sub_check=skip_sub_check
            )
        async with self._ensure_run_as_me(user_id) as bot:
            return await get_user(bot, skip_cache=skip_cache, skip_sub_check=True)

    async def get_user_fn(self, user: Union[str, BaseUser]) -> Optional[str]:
        if isinstance(user, str):
            user = await self.get_user(user)
        return user.fn

    async def get_user_comment(self, user: Union[str, BaseUser]) -> Optional[str]:
        if isinstance(user, str):
            user = await self.get_user(user)
        return user.comment

    async def get_user_note(self, user: Union[str, BaseUser]) -> Optional[str]:
        if isinstance(user, str):
            user = await self.get_user(user)
        return user.note

    async def get_user_staff(self, user: Union[str, BaseUser]) -> bool:
        if isinstance(user, str):
            user = await self.get_user(user)
        return user.staff

    async def get_user_verified(self, user: Union[str, BaseUser]) -> bool:
        if isinstance(user, str):
            user = await self.get_user(user)
        return user.verified

    async def set_user_meta(
        self,
        user: Union[str, BaseUser],
        *,
        public: Optional[Mapping[str, Any]] = None,
        trusted: Optional[Mapping[str, Any]] = None,
        private: Optional[Mapping[str, Any]] = None,
        attachments: Optional[Iterable[str]] = None,
        as_root: bool = False,
        use_proxy: bool = False,
    ) -> None:
        if isinstance(user, str):
            user_id = user
            user = await self.get_user(user)
        else:
            user_id = user.user_id
        set_desc = pb.SetDesc(
            public=to_json(public) if public else None,
            trusted=to_json(trusted) if trusted else None,
            private=to_json(private) if private else None,
        )
        async with self._ensure_run_as_me(user_id, use_proxy=use_proxy) as bot:
            await bot.set(
                "me",
                desc=set_desc,
                extra=pb.ClientExtra(attachments=attachments, auth_level=pb.ROOT if as_root else None),
            )
    
    async def set_user_public(self, user: Union[str, BaseUser], **kwds: Any) -> None:
        user = await self._ensure_user(user)
        public = user.public or {}
        public.update(**kwds)
        await self.set_user_meta(user, public=public, use_proxy=True)
    
    async def set_user_trusted(self, user: Union[str, BaseUser], **kwds: Any) -> None:
        user = await self._ensure_user(user)
        trusted = user.trusted or {}
        trusted.update(**kwds)
        await self.set_user_meta(user, trusted=trusted, as_root=True, use_proxy=True)
    
    async def set_user_private(self, user: Union[str, BaseUser], **kwds: Any) -> None:
        user = await self._ensure_user(user)
        private = user.private or {}
        private.update(**kwds)
        await self.set_user_meta(user, private=private, use_proxy=False)

    async def set_user_fn(self, user: Union[str, BaseUser], fn: str) -> None:
        await self.set_user_public(user, fn=fn)
    
    async def set_user_note(self, user: Union[str, BaseUser], note: str) -> None:
        await self.set_user_public(user, note=note)

    async def set_user_comment(self, user: Union[str, BaseUser], comment: str) -> None:
        await self.set_user_private(user, comment=comment)

    async def _ensure_user(self, user: Union[str, BaseUser]) -> BaseUser:
        if isinstance(user, str):
            return await self.get_user(user)
        else:
            return user

    @asynccontextmanager
    async def _ensure_run_as_me(self, user_id: str, *, use_proxy: bool = True) -> AsyncGenerator[Bot, None]:
        if user_id == self.bot.user_id:
            user_id = "me"
        if user_id == "me" or not use_proxy:
            yield self.bot
        else:
            async with run_bot(ProxyBot.from_bot(self.bot, user_id)) as proxy:
                yield proxy
