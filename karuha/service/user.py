from typing import Any, Dict, Iterable, Mapping, Optional, Tuple, TypedDict, Union

from pydantic_core import to_json
from tinode_grpc import pb
from google.protobuf.json_format import ParseDict
from pydantic import BaseModel

from .base import BaseService
from ..runner import add_bot, run_bot
from ..data.user import User, BaseUser, get_user
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
        add_bot(bot)
        return bot

    async def new_user(
        self,
        uname: str,
        password: str,
        *,
        tags: Iterable[str] = (),
        cred: Iterable[ClientCredType] = (),
        state: UserStateType = "ok"
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
        async with run_bot(ProxyBot.from_bot(self.bot, user_id)) as bot:
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
        if user_id == self.bot.user_id:
            user_id = "me"
        if user_id == "me":
            await self.bot.set("me", desc=set_desc)
        else:
            proxy = ProxyBot.from_bot(self.bot, user_id)
            async with run_bot(proxy):
                await proxy.set("me", desc=set_desc)
