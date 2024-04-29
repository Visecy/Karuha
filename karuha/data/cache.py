from typing import (FrozenSet, Iterable, List, Optional, Tuple, TypeVar, Union,
                    overload)

from pydantic import BaseModel
from tinode_grpc import pb

from ..event.message import MessageEvent

from ..bot import Bot
from ..event import on
from ..event.bot import MetaEvent
from ..store import (DataModel, MemoryStore, MessageBoundDataModel, PrimaryKey, TopicBoundDataModel,
                     UserBoundDataModel)
from ..text import Message
from .meta import (BaseDesc, BaseSubscription, CommonDesc, Cred,
                   GroupTopicDesc, P2PTopicDesc, Subscription, TopicInfo,
                   UserCred, UserDesc, UserTags)
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


class UserCache(UserBoundDataModel):
    desc: Optional[BaseDesc] = None
    tags: Optional[UserTags] = None
    cred: Optional[UserCred] = None


class GroupTopicCache(TopicBoundDataModel):
    desc: Optional[Union[BaseDesc, TopicInfo]] = None
    tags: Optional[UserTags] = None


class P2PTopicCache(DataModel):
    user_pair: PrimaryKey[FrozenSet[str]]
    desc: P2PTopicDesc


class SubscriptionCache(TopicBoundDataModel, UserBoundDataModel):
    sub: BaseSubscription


class MessageCache(MessageBoundDataModel):
    message: Message


user_cache = MemoryStore[UserCache]("user_meta_cache")
group_cache = MemoryStore[GroupTopicCache]("group_meta_cache")
p2p_cache = MemoryStore[P2PTopicCache]("p2p_meta_cache")
subscription_cache = MemoryStore[SubscriptionCache]("sub_meta_cache")
message_cache = MemoryStore[MessageCache]("message_cache")


def update_user_cache(
    user_id: str,
    desc: Optional[BaseDesc] = None,
    tags: Optional[UserTags] = None,
    cred: Optional[UserCred] = None,
) -> None:
    if user_id not in user_cache:
        user_cache.add(UserCache(user_id=user_id, desc=desc, tags=tags, cred=cred))
        return
    cache = user_cache[user_id]
    cache.desc = _update_model(cache.desc, desc)
    cache.tags = tags or cache.tags
    cache.cred = cred or cache.cred


def update_group_cache(
    topic: str,
    desc: Optional[Union[BaseDesc, TopicInfo]] = None,
    tags: Optional[List[str]] = None,
) -> None:
    if topic not in group_cache:
        group_cache.add(GroupTopicCache(topic=topic, desc=desc, tags=tags))
        return
    cache = group_cache[topic]
    cache.desc = _update_model(cache.desc, desc)
    cache.tags = tags or cache.tags


def update_p2p_cache(user1_id: str, user2_id: str, desc: P2PTopicDesc) -> None:
    user_pair = frozenset((user1_id, user2_id))
    if user_pair not in p2p_cache:
        p2p_cache.add(P2PTopicCache(user_pair=user_pair, desc=desc))
        return
    cache = p2p_cache[user_pair]
    cache.desc = _update_model(cache.desc, desc)


def update_sub_cache(topic: str, user_id: str, sub: BaseSubscription) -> None:
    if (topic, user_id) not in subscription_cache:
        subscription_cache.add(SubscriptionCache(topic=topic, user_id=user_id, sub=sub))
        return
    cache = subscription_cache[topic, user_id]
    cache.sub = _update_model(cache.sub, sub)


def update_message_cache(message: Message) -> None:
    if (message.topic, message.seq_id) not in message_cache:
        message_cache.add(MessageCache(topic=message.topic, seq_id=message.seq_id, message=message))
        return
    cache = message_cache[message.topic, message.seq_id]
    cache.message = message


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


async def _get_p2p_topic(bot: Bot, /, topic_id: str) -> TopicInfo:
    topic = group_cache.get(topic_id)
    if (
        topic is not None
        and topic.desc is not None
        and isinstance(topic.desc, TopicInfo)
    ):
        return topic.desc
    await ensure_sub(bot, topic_id)
    _, topic = await bot.get(topic_id, "desc")
    assert topic is not None
    return P2PTopicDesc.from_meta(topic.desc)


async def get_p2p_desc(bot: Bot, /, user_id: str) -> TopicInfo:
    if user_id.startswith("p2p"):
        desc = await _get_p2p_topic(bot, user_id)
        return desc
    assert user_id.startswith("usr"), "user_id must be a user"
    user_pair = frozenset((bot.uid, user_id))
    topic = p2p_cache.get(user_pair)
    if topic is not None:
        return topic.desc
    await ensure_sub(bot, user_id)
    _, topic = await bot.get(user_id, "desc")
    assert topic is not None
    return P2PTopicDesc.from_meta(topic.desc)


async def get_sub(bot: Bot, /, topic_id: str, *, ensure_meta: bool = False) -> BaseSubscription:
    assert topic_id != "me", "topic_id must not be 'me'"
    sub = subscription_cache.get((topic_id, bot.uid))
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
    sub = [(c.user_id, c.sub) for c in subscription_cache.values() if c.topic == topic_id]
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
    sub = [(c.topic, c.sub) for c in subscription_cache.values() if c.user_id == bot.uid]
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


def clear_meta_cache() -> None:
    user_cache.clear()
    p2p_cache.clear()
    group_cache.clear()
    subscription_cache.clear()
    message_cache.clear()


def cache_user(user_id: str, desc: pb.TopicDesc) -> None:
    user = UserDesc.from_meta(desc)
    update_user_cache(user_id, desc=user)


def cache_p2p_topic(user_id: str, topic_id: str, desc: pb.TopicDesc) -> None:
    topic = P2PTopicDesc.from_meta(desc)
    user = CommonDesc.from_meta(desc)
    sub = BaseSubscription.from_meta(desc)
    update_p2p_cache(user_id, topic_id, desc=topic)
    update_user_cache(user_id, desc=user)
    update_sub_cache(topic_id, user_id, sub)


def cache_group_topic(user_id: str, topic_id: str, desc: pb.TopicDesc) -> None:
    if topic_id.startswith("p2p"):
        topic = TopicInfo.from_meta(desc)
    else:
        topic = GroupTopicDesc.from_meta(desc)
    sub = BaseSubscription.from_meta(desc)
    update_group_cache(topic_id, topic)
    update_sub_cache(topic_id, user_id, sub)


def cache_me_subscription(user_id: str, sub_meta: pb.TopicSub) -> None:
    topic = sub_meta.topic
    assert topic
    sub = Subscription.from_meta(sub_meta)
    desc = BaseDesc.from_meta(sub_meta)
    update_sub_cache(topic, user_id, sub)
    if topic.startswith("usr"):
        update_user_cache(topic, desc=desc)
    else:
        update_group_cache(topic, desc=desc)


def cache_topic_subscription(topic: str, sub_meta: pb.TopicSub) -> None:
    user_id = sub_meta.user_id
    assert user_id
    sub = Subscription.from_meta(sub_meta)
    desc = BaseDesc.from_meta(sub_meta)
    update_sub_cache(topic, user_id, sub)
    update_user_cache(user_id, desc=desc)


def cache_tags(topic: str, tags: Iterable[str]) -> None:
    if topic.startswith("usr"):
        update_user_cache(topic, tags=list(tags))
    else:
        update_group_cache(topic, tags=list(tags))


@on(MetaEvent)
def handle_meta(event: MetaEvent) -> None:
    meta = event.server_message
    user = event.bot.uid
    topic = meta.topic
    if meta.desc:
        if topic == "me":
            cache_user(user, meta.desc)
        elif topic.startswith("usr"):
            cache_p2p_topic(user, topic, meta.desc)
        else:
            cache_group_topic(user, topic, meta.desc)
    if meta.sub:
        if topic == "me":
            for sub_meta in meta.sub:
                cache_me_subscription(user, sub_meta)
        else:
            for sub_meta in meta.sub:
                cache_topic_subscription(topic, sub_meta)
    if meta.tags:
        cache_tags(user if topic == "me" else topic, meta.tags)
    if meta.cred:
        assert topic == "me" or topic.startswith("usr")
        update_user_cache(
            topic,
            cred=[
                {"method": c.method, "value": c.value, "done": c.done}
                for c in meta.cred
            ],  # type: ignore
        )


@on(MessageEvent)
def handle_message(event: MessageEvent) -> None:
    update_message_cache(event.message)
