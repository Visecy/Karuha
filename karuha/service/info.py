from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Generic, Iterable, Literal, Mapping, Optional, TypeVar, Union
from tinode_grpc import pb
from pydantic_core import to_json

from ..bot import Bot, ProxyBot
from ..runner import run_bot
from ..data.cache import get_group_desc, get_user_desc, get_sub
from ..data.model import BaseInfo
from .base import BaseService


T_Info = TypeVar("T_Info", bound=BaseInfo)


class _BaseInfoService(BaseService, Generic[T_Info]):
    __slots__ = []

    async def get_public(self, info: Union[str, T_Info], /, skip_cache: bool = False) -> Optional[Mapping[str, Any]]:
        if isinstance(info, BaseInfo):
            return info.public
        if info.startswith("usr") or info == "me":
            desc = await get_user_desc(self.bot, info, skip_cache=skip_cache)
        else:
            desc = await get_group_desc(self.bot, info, skip_cache=skip_cache)
        return desc.public

    async def get_trusted(self, info: Union[str, T_Info], /, skip_cache: bool = False) -> Optional[Mapping[str, Any]]:
        if isinstance(info, BaseInfo):
            return info.trusted
        if info.startswith("usr") or info == "me":
            desc = await get_user_desc(self.bot, info, skip_cache=skip_cache)
        else:
            desc = await get_group_desc(self.bot, info, skip_cache=skip_cache)
        return desc.trusted

    async def get_private(self, info: Union[str, T_Info], /, skip_cache: bool = False) -> Optional[Mapping[str, Any]]:
        if isinstance(info, BaseInfo):
            return info.private
        sub = await get_sub(self.bot, info, skip_cache=skip_cache)
        return sub and sub.private

    async def get_fn(self, info: Union[str, T_Info], /, skip_cache: bool = False) -> Optional[str]:
        public = await self.get_public(info, skip_cache=skip_cache)
        if public:
            return public.get("fn")

    async def get_note(self, info: Union[str, T_Info], /, skip_cache: bool = False) -> Optional[str]:
        public = await self.get_public(info, skip_cache=skip_cache)
        if public:
            return public.get("note")

    async def get_comment(self, info: Union[str, T_Info], /, skip_cache: bool = False) -> Optional[str]:
        private = await self.get_private(info, skip_cache=skip_cache)
        if private:
            return private.get("comment")

    async def is_staff(self, info: Union[str, T_Info], /, skip_cache: bool = False) -> bool:
        trusted = await self.get_trusted(info, skip_cache=skip_cache)
        return bool(trusted and trusted.get("staff"))

    async def is_verified(self, info: Union[str, T_Info], /, skip_cache: bool = False) -> bool:
        trusted = await self.get_trusted(info, skip_cache=skip_cache)
        return bool(trusted and trusted.get("verified"))

    async def set_desc(
        self,
        info: Union[str, T_Info],
        *,
        public: Optional[Mapping[str, Any]] = None,
        trusted: Optional[Mapping[str, Any]] = None,
        private: Optional[Mapping[str, Any]] = None,
        attachments: Optional[Iterable[str]] = None,
        as_root: bool = False,
        use_proxy: bool = False,
        proxy_bot: Union[str, Bot, None] = None,
    ) -> None:
        id = info.id if isinstance(info, BaseInfo) else info
        set_desc = pb.SetDesc(
            public=to_json(public) if public else None,
            trusted=to_json(trusted) if trusted else None,
            private=to_json(private) if private else None,
        )
        async with self._run_proxy_bot(use_proxy=use_proxy, proxy_bot=proxy_bot) as bot:
            await bot.set(
                id,
                desc=set_desc,
                extra=pb.ClientExtra(attachments=attachments, auth_level=pb.ROOT if as_root else None),
            )

    async def set_public(
        self,
        info: Union[str, T_Info],
        /,
        data: Mapping[str, Any],
        *,
        update: bool = True,
        as_root: bool = False,
        **kwds: Any,
    ) -> None:
        if update:
            public = await self.get_public(info)
            public = dict(public) if public else {}
            public.update(data)
        else:
            public = data
        return await self.set_desc(info, public=public, as_root=as_root, **kwds)

    async def set_trusted(
        self,
        info: Union[str, T_Info],
        /,
        data: Mapping[str, Any],
        *,
        update: bool = True,
        as_root: Literal[True] = True,
        **kwds: Any,
    ) -> None:
        if update:
            trusted = await self.get_trusted(info)
            trusted = dict(trusted) if trusted else {}
            trusted.update(data)
        else:
            trusted = data
        return await self.set_desc(info, trusted=trusted, as_root=as_root, **kwds)

    async def set_private(
        self,
        info: Union[str, T_Info],
        /,
        data: Mapping[str, Any],
        *,
        update: bool = True,
        as_root: bool = False,
        **kwds: Any,
    ) -> None:
        if update:
            private = await self.get_private(info)
            private = dict(private) if private else {}
            private.update(data)
        else:
            private = data
        return await self.set_desc(info, private=private, as_root=as_root, **kwds)

    async def set_fn(self, info: Union[str, T_Info], /, fn: str, **kwds: Any) -> None:
        return await self.set_public(info, {"fn": fn}, update=True, **kwds)

    async def set_note(self, info: Union[str, T_Info], /, note: str, **kwds: Any) -> None:
        return await self.set_public(info, {"note": note}, update=True, **kwds)

    async def set_comment(self, info: Union[str, T_Info], /, comment: str, **kwds: Any) -> None:
        return await self.set_private(info, {"comment": comment}, update=True, **kwds)

    @asynccontextmanager
    async def _run_proxy_bot(self, use_proxy: bool, proxy_bot: Union[str, Bot, None]) -> AsyncGenerator[Bot, None]:
        if not use_proxy or proxy_bot is None:
            yield self.bot
        elif isinstance(proxy_bot, Bot):
            yield proxy_bot
        else:
            async with run_bot(ProxyBot.from_bot(self.bot, proxy_bot)) as bot:
                yield bot


class InfoService(_BaseInfoService[BaseInfo]):
    """
    Service to work with user and group descriptions.
    """

    __slots__ = []
