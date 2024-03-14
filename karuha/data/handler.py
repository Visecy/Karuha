from typing import Iterable
from tinode_grpc import pb

from ..event import on
from ..event.bot import LeaveEvent, MetaEvent, SubscribeEvent
from ..utils.decode import msg2dict
from .cache import (GroupTopicCache, P2PTopicCache, SubscriptionCache,
                    UserCache, group_cache, p2p_cache, subscription_cache,
                    user_cache)
from .meta import (BaseDesc, BaseSubscription, GroupTopicDesc, P2PTopicDesc,
                   Subscription, TopicInfo, UserDesc)
from .sub import _sub_topic, _leave_topic


def cache_user(user_id: str, desc: pb.TopicDesc) -> None:
    user = UserDesc.from_meta(desc)
    user_cache.add(UserCache(user=user_id, desc=user))


def cache_p2p_topic(user_id: str, topic_id: str, desc: pb.TopicDesc) -> None:
    topic = P2PTopicDesc.from_meta(desc)
    user = BaseDesc.from_meta(desc)
    sub = BaseSubscription.from_meta(desc)
    p2p_cache.add(P2PTopicCache(user_pair=frozenset((user_id, topic_id)), desc=topic))
    user_cache.add(UserCache(user=topic_id, desc=user))
    subscription_cache.add(SubscriptionCache(user=user_id, topic=topic_id, sub=sub))


def cache_group_topic(user_id: str, topic_id: str, desc: pb.TopicDesc) -> None:
    if topic_id.startswith("p2p"):
        topic = TopicInfo.from_meta(desc)
    else:
        topic = GroupTopicDesc.from_meta(desc)
    sub = BaseSubscription(
        acs=msg2dict(desc.acs),  # type: ignore
        private=desc.private  # type: ignore
    )
    group_cache.add(GroupTopicCache(topic=topic_id, desc=topic))
    subscription_cache.add(SubscriptionCache(user=user_id, topic=topic_id, sub=sub))


def cache_me_subscription(user_id: str, sub_meta: pb.TopicSub) -> None:
    topic = sub_meta.topic
    assert topic
    sub = Subscription(
        acs=msg2dict(sub_meta.acs),  # type: ignore
        private=sub_meta.private,  # type: ignore
        read=sub_meta.read_id,
        recv=sub_meta.recv_id,
        clear=sub_meta.del_id,
        updated=sub_meta.updated_at,  # type: ignore
        touched=sub_meta.touched_at,  # type: ignore
    )
    desc = BaseDesc(
        public=sub_meta.public,  # type: ignore
        trusted=sub_meta.trusted,  # type: ignore
    )
    subscription_cache.add(SubscriptionCache(user=user_id, topic=sub_meta.topic, sub=sub))
    if topic.startswith("usr"):
        user_cache.add(UserCache(user=topic, desc=desc))
    else:
        group_cache.add(GroupTopicCache(topic=topic, desc=desc))


def cache_topic_subscription(topic: str, sub_meta: pb.TopicSub) -> None:
    user_id = sub_meta.user_id
    assert user_id
    sub = Subscription(
        acs=msg2dict(sub_meta.acs),  # type: ignore
        private=sub_meta.private,  # type: ignore
        read=sub_meta.read_id,
        recv=sub_meta.recv_id,
        clear=sub_meta.del_id,
        updated=sub_meta.updated_at,  # type: ignore
        touched=sub_meta.touched_at,  # type: ignore
    )
    desc = BaseDesc(
        public=sub_meta.public,  # type: ignore
        trusted=sub_meta.trusted,  # type: ignore
    )
    subscription_cache.add(SubscriptionCache(user=user_id, topic=topic, sub=sub))
    user_cache.add(UserCache(user=user_id, desc=desc))


def cache_tags(topic: str, tags: Iterable[str]) -> None:
    if topic.startswith("usr"):
        user_cache.add(UserCache(user=topic, tags=tags))  # type: ignore
    else:
        group_cache.add(GroupTopicCache(topic=topic, tags=tags))  # type: ignore


@on(MetaEvent)
def cache_meta(event: MetaEvent) -> None:
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
                cache_topic_subscription(topic, sub_meta)
        else:
            for sub_meta in meta.sub:
                cache_me_subscription(user, sub_meta)
    if meta.tags:
        cache_tags(topic, meta.tags)
    if meta.cred:
        assert topic == "me" or topic.startswith("usr")
        user_cache.add(UserCache(user=topic, cred=meta.cred))  # type: ignore


@on(SubscribeEvent)
def handle_sub(event: SubscribeEvent) -> None:
    _sub_topic(event.bot, event.topic)


@on(LeaveEvent)
def handle_leave(event: LeaveEvent) -> None:
    _leave_topic(event.bot, event.topic)
