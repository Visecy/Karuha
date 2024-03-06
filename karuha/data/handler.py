from typing import Iterable
from tinode_grpc import pb

from ..event import on
from ..event.bot import MetaEvent
from ..utils.decode import msg2dict
from .cache import (GroupTopicCache, P2PTopicCache, SubscriptionCache,
                    UserCache, group_cache, p2p_cache, subscription_cache,
                    user_cache)
from .meta import (BaseDesc, BaseSubscription, GroupTopic, P2PTopic,
                   Subscription, User)


def cache_user(user_id: str, desc: pb.TopicDesc) -> None:
    user = User(
        public=desc.public,  # type: ignore
        trusted=desc.trusted,  # type: ignore
        state=desc.state,
        state_at=desc.state_at,  # type: ignore
        created=desc.created_at,  # type: ignore
        updated=desc.updated_at,  # type: ignore
        touched=desc.touched_at,  # type: ignore
        defacs=msg2dict(desc.defacs)  # type: ignore
    )
    user_cache.add(UserCache(user=user_id, desc=user))


def cache_p2p_topic(user_id: str, topic_id: str, desc: pb.TopicDesc) -> None:
    topic = P2PTopic(
        seq=desc.seq_id,
        read=desc.read_id,
        recv=desc.recv_id,
        clear=desc.del_id,
        created=desc.created_at,  # type: ignore
        updated=desc.updated_at,  # type: ignore
        touched=desc.touched_at,  # type: ignore
    )
    user = BaseDesc(
        public=desc.public,  # type: ignore
        trusted=desc.trusted,  # type: ignore
    )
    sub = BaseSubscription(
        acs=msg2dict(desc.acs),  # type: ignore
        private=desc.private  # type: ignore
    )
    p2p_cache.add(P2PTopicCache(user_pair={user_id, topic_id}, desc=topic))
    user_cache.add(UserCache(user=topic_id, desc=user))
    subscription_cache.add(SubscriptionCache(user=user_id, topic=topic_id, sub=sub))


def cache_group_topic(user_id: str, topic_id: str, desc: pb.TopicDesc) -> None:
    topic = GroupTopic(
        public=desc.public,  # type: ignore
        trusted=desc.trusted,  # type: ignore
        defacs=msg2dict(desc.defacs),  # type: ignore
        seq=desc.seq_id,
        read=desc.read_id,
        recv=desc.recv_id,
        clear=desc.del_id,
        created=desc.created_at,  # type: ignore
        updated=desc.updated_at,  # type: ignore
        touched=desc.touched_at,  # type: ignore
        is_chan=desc.is_chan
    )
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
