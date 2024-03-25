from typing import (Any, Dict, FrozenSet, ItemsView, Iterator, KeysView, List,
                    Mapping, Optional, Set, Tuple, TypeVar, Union, ValuesView,
                    overload)

from pydantic import BaseModel
from typing_extensions import Self

from ..bot import Bot
from .meta import (BaseDesc, BaseSubscription, Cred, GroupTopicDesc,
                   P2PTopicDesc, Subscription, TopicInfo, UserCred, UserDesc,
                   UserTags)
from .sub import ensure_sub


T = TypeVar("T", bound=BaseModel)


@overload
def _update_model(raw: T, model: T) -> T: ...
@overload
def _update_model(raw: Optional[T], model: Optional[T]) -> Optional[T]: ...

def _update_model(raw: Optional[T], model: Optional[T]) -> Optional[T]:  # noqa: E302
    if raw is None:
        return model
    elif model is None:
        return
    if type(raw) is not type(model) and issubclass(type(raw), type(model)):
        return raw.model_copy(update=model.model_dump(exclude_defaults=True))
    return model.model_copy()


class BaseCache(BaseModel):
    def update(self, item: Self) -> None:
        pass


class UserCache(BaseCache):
    user: str
    desc: Optional[BaseDesc] = None
    tags: Optional[UserTags] = None
    cred: Optional[UserCred] = None

    def update(self, item: Self) -> None:
        self.desc = _update_model(self.desc, item.desc)
        self.tags = item.tags or self.tags
        self.cred = item.cred or self.cred


class GroupTopicCache(BaseCache):
    topic: str
    desc: Optional[Union[BaseDesc, TopicInfo]] = None
    tags: Optional[UserTags] = None

    def update(self, item: Self) -> None:
        self.desc = _update_model(self.desc, item.desc)
        self.tags = item.tags or self.tags


class P2PTopicCache(BaseCache):
    user_pair: FrozenSet[str]
    desc: P2PTopicDesc

    def update(self, item: Self) -> None:
        self.desc = _update_model(self.desc, item.desc)


class SubscriptionCache(BaseCache):
    user: str
    topic: str
    sub: BaseSubscription

    def update(self, item: Self) -> None:
        self.sub = _update_model(self.sub, item.sub)


T_Cache = TypeVar("T_Cache", bound=BaseCache)


class CachePool(Mapping[Tuple[Any, ...], T_Cache]):
    __slots__ = ["primary_keys", "_pool"]

    def __init__(self, primary_keys: Set[str]) -> None:
        self._pool: Dict[Tuple[Any, ...], T_Cache] = {}
        self.primary_keys = primary_keys
    
    def add(self, item: T_Cache) -> None:
        key = self._get_key(item)
        if c := self.get(key):
            c.update(item)
        else:
            self._pool[key] = item
    
    def clear(self) -> None:
        self._pool.clear()

    def keys(self) -> KeysView[Tuple[Any, ...]]:
        return self._pool.keys()
    
    def values(self) -> ValuesView[T_Cache]:
        return self._pool.values()
    
    def items(self) -> ItemsView[Tuple[Any, ...], T_Cache]:
        return self._pool.items()
    
    def get(self, key: Any, default: Optional[T_Cache] = None) -> Optional[T_Cache]:
        if not isinstance(key, tuple):
            key = (key,)
        return self._pool.get(key, default)
    
    def discard(self, key: Any) -> None:
        if not isinstance(key, tuple):
            if isinstance(key, BaseCache):
                key = self._get_key(key)  # type: ignore
            else:
                key = (key,)
        self._pool.pop(key, None)
    
    def __getitem__(self, key: Any) -> T_Cache:
        if not isinstance(key, tuple):
            if isinstance(key, BaseCache):
                key = self._get_key(key)  # type: ignore
            else:
                key = (key,)
        return self._pool[key]
    
    def __delitem__(self, key: Any) -> None:
        if not isinstance(key, tuple):
            if isinstance(key, BaseCache):
                key = self._get_key(key)  # type: ignore
            else:
                key = (key,)
        del self._pool[key]
    
    def __iter__(self) -> Iterator[Tuple[Any, ...]]:
        yield from self._pool
    
    def __contains__(self, __key: object) -> bool:
        return __key in self._pool
    
    def __len__(self) -> int:
        return len(self._pool)

    def _get_key(self, item: T_Cache) -> Tuple[Any, ...]:
        return tuple(item.model_dump(include=self.primary_keys).values())


user_cache = CachePool[UserCache]({"user"})
group_cache = CachePool[GroupTopicCache]({"topic"})
p2p_cache = CachePool[P2PTopicCache]({"user_pair"})
subscription_cache = CachePool[SubscriptionCache]({"user", "topic"})


async def get_user_desc(bot: Bot, /, user_id: str, *, ensure_meta: bool = False) -> BaseDesc:
    assert user_id.startswith("usr") or user_id == "me", "user_id must be a user"
    if user_id == "me":
        user = user_cache.get(bot.uid)
    else:
        assert not ensure_meta, "only 'me' can be used with ensure_meta=True"
        user = user_cache.get(user_id)
    if user is not None and user.desc is not None and (not ensure_meta or isinstance(user.desc, UserDesc)):
        return user.desc
    await ensure_sub(bot, user_id)
    _, user = await bot.get(user_id, "desc")
    assert user is not None
    return UserDesc.from_meta(user.desc)


async def get_group_desc(
    bot: Bot, /, topic_id: str, *, ensure_meta: bool = False
) -> BaseDesc:
    assert topic_id.startswith("grp"), "topic_id must be a group topic"
    topic = group_cache.get(topic_id)
    if (
        topic is not None
        and topic.desc is not None
        and isinstance(topic.desc, BaseDesc)
        and (not ensure_meta or isinstance(topic.desc, GroupTopicDesc))
    ):
        return topic.desc
    await ensure_sub(bot, topic_id)
    _, topic = await bot.get(topic_id, "desc")
    assert topic is not None
    return GroupTopicDesc.from_meta(topic.desc)


async def _get_p2p_topic(
    bot: Bot, /, topic_id: str, *, ensure_meta: bool = False
) -> TopicInfo:
    topic = group_cache.get(topic_id)
    if (
        topic is not None
        and topic.desc is not None
        and isinstance(topic.desc, TopicInfo)
        and (not ensure_meta or isinstance(topic.desc, P2PTopicDesc))
    ):
        return topic.desc
    await ensure_sub(bot, topic_id)
    _, topic = await bot.get(topic_id, "desc")
    assert topic is not None
    return P2PTopicDesc.from_meta(topic.desc)


async def get_p2p_desc(bot: Bot, /, user_id: str, *, ensure_meta: bool = False) -> TopicInfo:
    if user_id.startswith("p2p"):
        desc = await _get_p2p_topic(bot, user_id, ensure_meta=ensure_meta)
        return desc
    assert user_id.startswith("usr"), "user_id must be a user"
    user_pair = frozenset((bot.uid, user_id))
    topic = p2p_cache.get(user_pair)
    if topic is not None and (not ensure_meta or isinstance(topic.desc, P2PTopicDesc)):
        return topic.desc
    await ensure_sub(bot, user_id)
    _, topic = await bot.get(user_id, "desc")
    assert topic is not None
    return P2PTopicDesc.from_meta(topic.desc)


async def get_sub(bot: Bot, /, topic_id: str, *, ensure_meta: bool = False) -> BaseSubscription:
    assert topic_id != "me", "topic_id must not be 'me'"
    sub = subscription_cache.get((bot.uid, topic_id))
    if sub is not None and (not ensure_meta or isinstance(sub.sub, Subscription)):
        return sub.sub
    await ensure_sub(bot, topic_id)
    _, sub_meta = await bot.get("me", "sub")
    assert sub_meta is not None
    for i in sub_meta.sub:
        if i.user_id == bot.uid:
            return Subscription.from_meta(i)
    raise ValueError(f"bot not subscribed to topic {topic_id}")


async def get_topic_sub(
    bot: Bot, /, topic_id: str, *, ensure_meta: bool = False, ensure_all: bool = True
) -> List[Tuple[str, BaseSubscription]]:
    assert topic_id != "me", "topic_id must not be 'me'"
    sub = [(c.user, c.sub) for c in subscription_cache.values() if c.topic == topic_id]
    if (
        sub
        and not ensure_all
        and (not ensure_meta or all(isinstance(s[1], Subscription) for s in sub))
    ):
        return sub
    await ensure_sub(bot, topic_id)
    _, sub_meta = await bot.get(topic_id, "sub")
    assert sub_meta is not None
    return [(s.user_id, Subscription.from_meta(s)) for s in sub_meta.sub]


async def get_my_sub(
    bot: Bot, /, *, ensure_meta: bool = False, ensure_all: bool = True
) -> List[Tuple[str, BaseSubscription]]:
    sub = [(c.topic, c.sub) for c in subscription_cache.values() if c.user == bot.uid]
    if (
        sub
        and not ensure_all
        and (not ensure_meta or all(isinstance(s[1], Subscription) for s in sub))
    ):
        return sub
    await ensure_sub(bot, "me")
    _, sub_meta = await bot.get("me", "sub")
    assert sub_meta is not None
    return [(s.topic, Subscription.from_meta(s)) for s in sub_meta.sub]


async def get_user_tags(bot: Bot) -> List[str]:
    cache = user_cache.get(bot.uid)
    if cache is not None and cache.tags is not None:
        return cache.tags.copy()
    await ensure_sub(bot, "me")
    _, tag_meta = await bot.get("me", "tags")
    assert tag_meta is not None
    return list(tag_meta.tags)


async def get_user_cred(bot: Bot) -> List[Cred]:
    cache = user_cache.get(bot.uid)
    if cache is not None and cache.cred is not None:
        return cache.cred.copy()
    await ensure_sub(bot, "me")
    _, cred_meta = await bot.get("me", "cred")
    assert cred_meta is not None
    return [Cred(method=c.method, value=c.value, done=c.done) for c in cred_meta.cred]
