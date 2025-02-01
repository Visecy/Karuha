from typing import Any, Dict, Iterable, Mapping, Optional, Tuple, Union

from tinode_grpc import pb

from ..data.model import ClientDesc, DefaultAccess

from .info import _BaseInfoService
from ..data.user import BaseUser, get_user
from ..data.types import ClientDescType, ClientCredType, UserStateType
from ..bot import Bot
from ..utils.decode import dict2msg


class UserService(_BaseInfoService[BaseUser]):
    """
    Service for user management.
    """

    __slots__ = []

    async def new_user(
        self,
        uname: str,
        password: str,
        *,
        fn: Optional[str] = None,
        default_acs: Optional[DefaultAccess] = None,
        public: Optional[Dict[str, Any]] = None,
        trusted: Optional[Dict[str, Any]] = None,
        private: Optional[Dict[str, Any]] = None,
        desc: Optional[ClientDescType] = None,
        tags: Iterable[str] = (),
        cred: Iterable[ClientCredType] = (),
        state: Optional[UserStateType] = None,
    ) -> Tuple[str, Optional[str]]:
        secret = f"{uname}:{password}"
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
        _, params = await self.bot.account(
            "new",
            "basic",
            secret.encode(),
            do_login=False,
            desc=dict2msg(desc, pb.SetDesc) if desc is not None else desc,
            state=state,
            tags=tags,
            cred=(dict2msg(c, pb.ClientCred) for c in cred),
        )
        user_id = params["user"]
        token = params.get("token")
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
            return await get_user(self.bot, user_id, skip_cache=skip_cache, skip_sub_check=skip_sub_check)
        async with self._run_proxy_bot(use_proxy=use_proxy, proxy_bot=user_id) as bot:
            return await get_user(bot, skip_cache=skip_cache, skip_sub_check=True)

    async def set_desc(
        self,
        user: Union[str, BaseUser],
        *,
        public: Optional[Mapping[str, Any]] = None,
        trusted: Optional[Mapping[str, Any]] = None,
        private: Optional[Mapping[str, Any]] = None,
        attachments: Optional[Iterable[str]] = None,
        as_root: bool = False,
        use_proxy: bool = False,
        proxy_bot: Union[str, Bot, None] = None,
    ) -> None:
        id = user.id if isinstance(user, BaseUser) else user
        if id == self.bot.user_id:
            id = "me"
        if id == "me":
            use_proxy = False
        elif use_proxy:
            if proxy_bot is not None:
                raise ValueError("cannot specify proxy bot for user description setting")
            proxy_bot = id
            id = "me"
        return await super().set_desc(
            id,
            public=public,
            trusted=trusted,
            private=private,
            attachments=attachments,
            as_root=as_root,
            use_proxy=use_proxy,
            proxy_bot=proxy_bot,
        )

    async def set_public(
        self,
        user: Union[str, BaseUser],
        /,
        data: Mapping[str, Any],
        *,
        update: bool = True,
        use_proxy: bool = True,
        **kwds: Any,
    ) -> None:
        return await super().set_public(user, data, update=update, use_proxy=use_proxy, **kwds)

    async def set_trusted(
        self,
        user: Union[str, BaseUser],
        /,
        data: Mapping[str, Any],
        *,
        update: bool = True,
        use_proxy: bool = True,
        **kwds: Any,
    ) -> None:
        return await super().set_trusted(user, data, update=update, use_proxy=use_proxy, **kwds)

    async def del_user(self, user: Union[str, BaseUser], /, *, hard: bool = False) -> None:
        id = user.id if isinstance(user, BaseUser) else user
        await self.bot.delete("user", user_id=id, hard=hard)
