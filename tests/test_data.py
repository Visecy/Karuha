import asyncio
from pydantic_core import to_json
from tinode_grpc import pb

from karuha.data.cache import UserCache, clear_cache, get_user_cred, get_user_tags, update_user_cache, user_cache
from karuha.data.meta import BaseDesc, UserDesc
from karuha.data.model import AccessPermission, Cred
from karuha.data.sub import has_sub
from karuha.data.topic import BaseTopic, Topic, TopicSub, get_topic, get_topic_list
from karuha.data.user import BaseUser, User, get_user

from .utils import AsyncBotTestCase


class TestData(AsyncBotTestCase):
    def test_access(self) -> None:
        self.assertEqual(
            AccessPermission.model_validate("N"),
            AccessPermission()
        )
        self.assertEqual(
            AccessPermission.model_validate(""),
            AccessPermission()
        )
        self.assertEqual(
            AccessPermission.model_validate("JRWPASDO"),
            AccessPermission(
                join=True,
                read=True,
                write=True,
                presence=True,
                approve=True,
                sharing=True,
                delete=True,
                owner=True,
            )
        )
        self.assertEqual(
            AccessPermission.model_validate("RWRWJ"),
            AccessPermission(
                join=True,
                read=True,
                write=True,
            )
        )
        with self.assertRaises(ValueError):
            AccessPermission.model_validate("NJRW")
        self.assertEqual(
            AccessPermission(
                join=True,
                read=True,
                write=True,
            ).model_dump(),
            'JRW'
        )
        self.assertEqual(
            AccessPermission().model_dump(),
            "N"
        )

    def test_cache(self) -> None:
        base_desc = BaseDesc(
            public=b"{\"fn\": \"test\"}",  # type: ignore
            trusted=None
        )
        cache = user_cache.get("user")
        self.assertIsNone(cache)
        user_cache.add(UserCache(user_id="user", desc=base_desc))
        cache = user_cache.get("user")
        assert cache and isinstance(cache.desc, BaseDesc)
        self.assertEqual(cache.desc, base_desc)

        desc = UserDesc(
            created=1709214504076,  # type: ignore
            updated=1709466962755,  # type: ignore
            public=b"{\"fn\": \"user\"}",  # type: ignore
            trusted=b"{\"staff\": true}"  # type: ignore
        )
        update_user_cache(user_id="user", desc=desc)
        cache = user_cache.get("user")
        assert cache and isinstance(cache.desc, UserDesc)
        self.assertEqual(cache.desc, desc)

        update_user_cache(user_id="user", desc=base_desc)
        cache = user_cache.get("user")
        assert cache and isinstance(cache.desc, UserDesc)
        self.assertEqual(cache.desc.public, base_desc.public)
        self.assertEqual(cache.desc.created, desc.created)

    async def test_me_meta(self) -> None:
        task = asyncio.create_task(get_user(self.bot, skip_cache=True))
        get_msg = await self.bot.consum_message()
        assert get_msg.get
        get_msg = get_msg.get
        meta = pb.ServerMeta(
            id=get_msg.id,
            topic="me",
            desc=pb.TopicDesc(
                created_at=1709214504076,
                updated_at=1709466962755,
                touched_at=1709466962755,
                defacs=pb.DefaultAcsMode(
                    auth="JRWPAS",
                    anon="N"
                ),
                acs=pb.AccessMode(
                    want="JPS",
                    given="JPS"
                ),
                public=to_json({"note": "test note"}),
                trusted=to_json({"staff": True}),
                state="ok"
            )
        )
        self.bot.receive_message(pb.ServerMsg(meta=meta))
        user = await self.wait_for(task)
        self.assertIsInstance(user, User)
        self.assertIsNone(user.fn)
        self.assertEqual(user.note, "test note")
        self.assertTrue(user.staff)
        self.assertFalse(user.verified)

    async def test_me_sub_meta(self) -> None:
        clear_cache()
        task = asyncio.create_task(get_topic_list(self.bot, ensure_all=True))
        get_msg = await self.bot.consum_message()
        assert get_msg.HasField("get"), get_msg
        get_msg = get_msg.get
        meta = pb.ServerMeta(
            id=get_msg.id,
            topic="me",
            sub=[
                pb.TopicSub(
                    updated_at=1707738410676,
                    acs=pb.AccessMode(
                        want="JRWPA",
                        given="JRWPA"
                    ),
                    read_id=2,
                    recv_id=2,
                    topic="usr_test_1",
                    touched_at=1707738410960,
                    seq_id=2
                ),
                pb.TopicSub(
                    updated_at=1708326544978,
                    acs=pb.AccessMode(
                        want="JRWPS",
                        given="JRWPASD"
                    ),
                    read_id=70,
                    recv_id=70,
                    public=to_json({"fn": "Test Group"}),
                    private=to_json({"note": "test note"}),
                    topic="grp_test_1",
                    touched_at=1708326545004,
                    seq_id=70,
                    del_id=3
                )
            ]
        )
        self.bot.receive_message(pb.ServerMsg(meta=meta))
        subs = await self.wait_for(task)
        self.assertEqual(len(subs), 2)
        for sub in subs:
            assert isinstance(sub, TopicSub)
            if sub.topic == "grp_test_1":
                self.assertEqual(sub.public, {"fn": "Test Group"})
                self.assertIsNotNone(sub.touched)
                self.assertEqual(sub.read, 70)
                self.assertEqual(sub.recv, 70)
                assert sub.acs
                self.assertEqual(
                    sub.acs.want,
                    AccessPermission(
                        join=True, read=True, write=True, presence=True, sharing=True
                    ),
                )
            elif sub.topic == "usr_test_1":
                self.assertIsNone(sub.public)
                self.assertEqual(sub.read, 2)
                self.assertEqual(sub.recv, 2)
            else:
                assert False, f"unexpected topic: {sub.topic}"
        
        user = await get_user(self.bot, "usr_test_1")
        self.assertIsInstance(user, BaseUser)
        self.assertEqual(user.user_id, "usr_test_1")
        self.assertIsNone(user.fn)
        self.assertIsNone(user.note)
        self.assertIsNone(user.comment)
        self.assertFalse(user.verified)
        self.assertFalse(user.staff)

        topic = await get_topic(self.bot, "grp_test_1")
        self.assertIsInstance(topic, BaseTopic)
        self.assertEqual(topic.topic, "grp_test_1")
        self.assertEqual(topic.fn, "Test Group")
        self.assertIsNone(topic.note)
        self.assertIsNone(topic.comment)
        self.assertFalse(topic.verified)

        topic = await get_topic(self.bot, "usr_test_1")
        self.assertIsInstance(topic, BaseTopic)
        self.assertEqual(topic.topic, "usr_test_1")
        self.assertIsNone(topic.fn)
        self.assertIsNone(topic.note)
        self.assertIsNone(topic.comment)
        self.assertFalse(topic.verified)
    
    async def test_tag_and_cred(self) -> None:
        task = asyncio.create_task(get_user_tags(self.bot))
        get_msg = await self.bot.consum_message()
        assert get_msg.get
        get_msg = get_msg.get
        meta = pb.ServerMeta(
            id=get_msg.id,
            topic="me",
            tags=["basic:test"]
        )
        self.bot.receive_message(pb.ServerMsg(meta=meta))
        tags = await self.wait_for(task)
        self.assertEqual(tags, ["basic:test"])

        task = asyncio.create_task(get_user_cred(self.bot))
        get_msg = await self.bot.consum_message()
        assert get_msg.get
        get_msg = get_msg.get
        meta = pb.ServerMeta(
            id=get_msg.id,
            topic="me",
            cred=[pb.ServerCred(
                method="email",
                value="test@example.com"
            )]
        )
        self.bot.receive_message(pb.ServerMsg(meta=meta))
        cred = await self.wait_for(task)
        self.assertEqual(cred, [Cred(method="email", value="test@example.com")])
    
    async def test_p2p_meta(self) -> None:
        clear_cache()
        task = asyncio.create_task(get_topic(self.bot, "usr_test_1", skip_cache=True))
    
        get_msg = await self.bot.consum_message()
        assert get_msg.HasField("get")
        get_msg = get_msg.get
        self.assertEqual(get_msg.query.what, "desc")
        meta = pb.ServerMeta(
            id=get_msg.id,
            topic="usr_test_1",
            desc=pb.TopicDesc(
                created_at=1684421151062,
                updated_at=1684421151062,
                touched_at=1709023886332,
                acs=pb.AccessMode(), # want="JRWPA", given="JRWPAS"
                # seq_id=285,
                # read_id=285,
                # recv_id=285,
                # del_id=22,
                public=to_json({"fn": "Test User"}),
                # last_seen_time=1709705329000,
                # last_seen_user_agent="Tindroid/0.22.12 (Android 11; zh_CN); tindroid/0.22.12"
            )
        )
        self.bot.receive_message(pb.ServerMsg(meta=meta))

        self.bot.receive_message(pb.ServerMsg(meta=meta))
        topic = await self.wait_for(task)
        assert isinstance(topic, Topic)
        self.assertEqual(topic.topic, "usr_test_1")
        self.assertEqual(topic.fn, "Test User")
        self.assertIsNone(topic.note)
        self.assertIsNone(topic.defacs)
    
    async def test_topic_meta(self) -> None:
        clear_cache()
        task = asyncio.create_task(get_topic(self.bot, "grp_test_1"))

        get_msg = await self.bot.consum_message()
        assert get_msg.HasField("get")
        get_msg = get_msg.get
        meta = pb.ServerMeta(
            id=get_msg.id,
            topic="grp_test_1",
            desc=pb.TopicDesc(
                created_at=1683631963729,
                updated_at=1685376852448,
                touched_at=1710167311762,
                defacs={"auth": "JRWPS", "anon": "N"},
                acs={"want": "JRWPS", "given": "JRWPS"},
                seq_id=122,
                read_id=121,
                recv_id=121,
                del_id=2,
                public=to_json({"fn": "Test Group", "note": "Test Group Note"}),
                is_chan=True
            )
        )
        self.bot.receive_message(pb.ServerMsg(meta=meta))
        
        topic = await self.wait_for(task)
        assert isinstance(topic, Topic)
        self.assertEqual(topic.topic, "grp_test_1")
        self.assertEqual(topic.fn, "Test Group")
        self.assertEqual(topic.note, "Test Group Note")
        self.assertIsNone(topic.comment)
        self.assertEqual(topic.seq, 122)
        assert topic.defacs
        self.assertEqual(
            topic.defacs.auth,
            AccessPermission(join=True, read=True, write=True, presence=True, sharing=True)
        )
        assert topic.acs
        self.assertEqual(
            topic.acs.want,
            AccessPermission(join=True, read=True, write=True, presence=True, sharing=True)
        )
        self.assertTrue(topic.is_chan)
    
    async def test_sub(self) -> None:
        self.assertFalse(has_sub(self.bot, "test"))
