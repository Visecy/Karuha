from typing import (Any, Dict, ItemsView, Iterator, KeysView, Mapping,
                    Optional, Set, Tuple, TypeVar, Union, ValuesView, overload)
from typing_extensions import Self

from pydantic import BaseModel

from .meta import BaseDesc, TopicInfo, BaseSubscription, User, UserCred, UserTags


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
    if type(raw) is not type(model) and issubclass(type(model), type(raw)):
        return model.model_copy()
    return raw.model_copy(update=model.model_dump(exclude_defaults=True))


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
    desc: Optional[BaseDesc] = None
    tags: Optional[UserTags] = None

    def update(self, item: Self) -> None:
        self.desc = _update_model(self.desc, item.desc)
        self.tags = item.tags or self.tags


class P2PTopicCache(BaseCache):
    user_pair: Set[str]
    desc: TopicInfo

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
