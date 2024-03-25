import asyncio
import json
import aiofiles
import greenback
from pydantic import ValidationError
from tinode_grpc import pb

from karuha.data.cache import UserCache, user_cache
from karuha.data.meta import AccessPermission, BaseDesc, UserDesc
from karuha.data.store import (DataModel, JsonFileStore, MemoryStore,
                               PrimaryKey, get_store, is_pk_annotation)

from .utils import TEST_TIME_OUT, AsyncBotTestCase


class DataNoPk(DataModel, pk=()):
    content: str


class DataPk1(DataModel, pk="pk1"):
    pk1: str
    content: str


class DataPk2(DataModel):
    pk1: PrimaryKey[str]
    pk2: PrimaryKey[str]
    content: str


class JsonFileSyncStore(JsonFileStore[DataPk1]):
    enable_async_backend = False


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

    def test_data_model(self) -> None:
        self.assertTrue(is_pk_annotation(PrimaryKey))
        self.assertTrue(is_pk_annotation(PrimaryKey[int]))

        self.assertEqual(DataNoPk.__primary_key__, None)
        data = DataNoPk(content="test")
        self.assertEqual(data.content, "test")
        with self.assertRaises(AssertionError):
            data.get_primary_key()
        
        self.assertEqual(DataPk1.__primary_key__, ("pk1",))
        data = DataPk1(pk1="test", content="test")
        self.assertEqual(data.get_primary_key(), "test")
        with self.assertRaises(ValidationError):
            data.pk1 = "test1"
        self.assertEqual(data.pk1, "test")

        self.assertEqual(DataPk2.__primary_key__, ("pk1", "pk2"))
        data = DataPk2(pk1="test1", pk2="test2", content="test")
        self.assertEqual(set(data.get_primary_key()), set(("test1", "test2")))
    
    def test_memory_store(self) -> None:
        store = MemoryStore[DataModel]('test')
        self.assertIsInstance(store, MemoryStore)
        self.assertIs(store.data_type, DataModel)

        self.assertEqual(store.get_all(), [])
        self.assertEqual(tuple(store.keys()), ())
        self.assertEqual(tuple(store.values()), ())
        self.assertEqual(tuple(store.items()), ())

        self.assertIsNone(store.get("test"))
        data = DataPk1(pk1="test", content="test_content")
        self.assertIsNone(data.data_store)
        data.update()
        store.add(data, copy=True)
        self.assertIsNone(data.data_store)
        self.assertEqual(store["test"].model_dump(), data.model_dump())
        self.assertIsNot(store["test"], data)

        data = store["test"]
        self.assertIs(data.data_store, store)
        data.set_data_store(store)
        data.content = "test_content2"
        self.assertEqual(data.content, "test_content2")  # type: ignore

        data1 = DataNoPk(content="test_content")
        store.add(data1, copy=False)
        self.assertEqual(list(store.get_all()), [data1, data])
        self.assertEqual(list(store), [data1, data])
        self.assertEqual(list(store.values()), [data])
        self.assertEqual(list(store.keys()), ["test"])
        self.assertEqual(list(store.items()), [("test", data)])
        self.assertEqual(len(store), 2)
        self.assertIn("test", store)
        self.assertIn(data, store)
        self.assertIn(data1, store)

        store.remove(data)
        self.assertEqual(list(store.get_all()), [data1])
        self.assertNotIn(data, store)
        store.remove(data1)
        self.assertEqual(list(store.get_all()), [])
        self.assertNotIn(data1, store)

        self.assertFalse(store.discard(data))
        self.assertFalse(store.discard(data1))
        self.assertFalse(store)

    async def test_json_store(self) -> None:
        await greenback.ensure_portal()
        store = get_store("json", data_type=DataPk1)
        self.assertIsInstance(store, JsonFileStore)
        self.assertIs(store, get_store("json", data_type=DataPk1))
        self.assertTrue(store.async_backend_available())
        store.clear()
        self.assertTrue(not store._load_tasks or all(t.done() for t in store._load_tasks))
        self.assertTrue(store._save_tasks)
        await store.wait_tasks()
        self.assertFalse(store._should_wait())
        
        async with aiofiles.open(store.path, "rb") as f:
            content = await f.read()
        self.assertEqual(content, store.encode_data())
        self.assertEqual(json.loads(content), [])

        data = DataPk1(pk1="test", content="test")
        store.add(data)
        self.assertTrue(store._save_tasks)
        self.assertIs(data, store["test"])
        await store.wait_tasks()

        async with aiofiles.open(store.path, "rb") as f:
            content = await f.read()
        self.assertEqual(json.loads(content), [data.model_dump()])

        data.content = "test2"
        self.assertTrue(store._save_tasks)
        await store.wait_tasks()
        async with aiofiles.open(store.path, "rb") as f:
            content = await f.read()
        self.assertEqual(json.loads(content), [data.model_dump()])

        store.load_backend()
        store.save_backend()
        store.load_backend()
        store.save_backend()
        store.save_backend()
        await asyncio.wait_for(store.wait_tasks(), timeout=TEST_TIME_OUT)
        self.assertFalse(store._should_wait())
    
    def test_sync_json_store(self) -> None:
        store = JsonFileSyncStore.get_store(indent=4)
        self.assertFalse(store.enable_async_backend)
        store.clear()
        
        data = DataPk1(pk1="test", content="test")
        store.add(data)
        self.assertFalse(store._save_tasks)
        self.assertEqual(store.get_all(), [data])
        self.assertEqual(store.get("test"), data)

        with open(store.path, "rb") as f:
            content = f.read()
        self.assertEqual(json.loads(content), [data.model_dump()])
