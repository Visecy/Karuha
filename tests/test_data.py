from tinode_grpc import pb

from karuha.data.meta import AccessPermission, BaseDesc, UserDesc
from karuha.data.cache import UserCache, user_cache

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
    
    def test_cache(self) -> None:
        base_desc = BaseDesc(
            public=b"{\"fn\": \"test\"}",  # type: ignore
            trusted=None
        )
        cache = user_cache.get("user")
        self.assertIsNone(cache)
        user_cache.add(UserCache(user="user", desc=base_desc))
        cache = user_cache.get("user")
        assert cache and isinstance(cache.desc, BaseDesc)
        self.assertEqual(cache.desc, base_desc)
        
        desc = UserDesc(
            created=1709214504076,  # type: ignore
            updated=1709466962755,  # type: ignore
            public=b"{\"fn\": \"user\"}",  # type: ignore
            trusted=b"{\"staff\": true}"  # type: ignore
        )
        user_cache.add(UserCache(user="user", desc=desc))
        cache = user_cache.get("user")
        assert cache and isinstance(cache.desc, UserDesc)
        self.assertEqual(cache.desc, desc)

        user_cache.add(UserCache(user="user", desc=base_desc))
        cache = user_cache.get("user")
        assert cache and isinstance(cache.desc, UserDesc)
        self.assertEqual(cache.desc.public, base_desc.public)
        self.assertEqual(cache.desc.created, desc.created)

    async def test_meta(self) -> None:
        meta = pb.ServerMeta(
            id="102",
            topic="me",
            desc=pb.TopicDesc(
                created_at=1709214504076,
                updated_at=1709466962755,
                touched_at=1709466962755,
                defacs=pb.DefaultAcsMode(
                    auth="JRWPAS",
                    anon="N"
                )
            )
        )
        self.bot.receive_message(pb.ServerMsg(meta=meta))

