import asyncio
from unittest import IsolatedAsyncioTestCase

import aiofiles
import greenback
from pydantic import ValidationError
from pydantic_core import from_json

from karuha.store import DataModel, JsonFileStore, MemoryStore, PrimaryKey, get_store, is_pk_annotation, T_Data
from karuha.utils.invoker import HandlerInvoker

from .utils import TEST_TIMEOUT


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


class TestStore(IsolatedAsyncioTestCase):
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
        self.assertEqual(set(data.get_primary_key()), {"test1", "test2"})

    def test_memory_store(self) -> None:
        self.assertIs(MemoryStore.__store_type_var__, T_Data)
        store = MemoryStore[DataModel]("test")
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

    def test_store_dependency(self) -> None:
        def store_getter(store: MemoryStore[DataNoPk]) -> MemoryStore:
            return store

        s1 = HandlerInvoker().call_handler(store_getter)
        self.assertIsInstance(s1, MemoryStore)
        self.assertEqual(s1.name, "dependency-store_getter-store")
        self.assertEqual(s1.data_type, DataNoPk)
        s2 = HandlerInvoker().call_handler(store_getter)
        self.assertIs(s1, s2)

    def test_lru_store(self) -> None:
        store = get_store("lru", maxlen=3, data_type=DataPk1)
        store.add(DataPk1(pk1="test1", content="test1"))
        store.add(DataPk1(pk1="test2", content="test2"))
        store.add(DataPk1(pk1="test3", content="test3"))
        self.assertEqual([d.content for d in store.get_all()], ["test1", "test2", "test3"])
        store.add(DataPk1(pk1="test4", content="test4"))
        self.assertEqual([d.content for d in store.get_all()], ["test2", "test3", "test4"])
        t2 = store["test2"]
        self.assertEqual([d.content for d in store.get_all()], ["test3", "test4", "test2"])
        with self.assertRaises(KeyError):
            store["test1"]
        store.remove(store["test3"])
        self.assertEqual([d.content for d in store.get_all()], ["test4", "test2"])
        store.add(DataPk1(pk1="test5", content="test5"))
        self.assertEqual([d.content for d in store.get_all()], ["test4", "test2", "test5"])
        t2.content = "test2_new"
        self.assertEqual([d.content for d in store.get_all()], ["test4", "test5", "test2_new"])
        self.assertTrue(store.discard(t2))
        self.assertEqual([d.content for d in store.get_all()], ["test4", "test5"])
        self.assertFalse(store.discard(t2))

    async def test_json_store(self) -> None:
        await greenback.ensure_portal()
        self.assertIs(JsonFileStore.__store_type_var__, T_Data)
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
        self.assertEqual(from_json(content), [])

        data = DataPk1(pk1="test", content="test")
        store.add(data)
        self.assertTrue(store._save_tasks)
        self.assertIs(data, store["test"])
        await store.wait_tasks()

        async with aiofiles.open(store.path, "rb") as f:
            content = await f.read()
        self.assertEqual(from_json(content), [data.model_dump()])

        data.content = "test2"
        self.assertTrue(store._save_tasks)
        await store.wait_tasks()
        async with aiofiles.open(store.path, "rb") as f:
            content = await f.read()
        self.assertEqual(from_json(content), [data.model_dump()])

        store.load_backend()
        store.save_backend()
        store.load_backend()
        store.save_backend()
        store.save_backend()
        await asyncio.wait_for(store.wait_tasks(), timeout=TEST_TIMEOUT)
        self.assertFalse(store._should_wait())

    def test_sync_json_store(self) -> None:
        store = JsonFileSyncStore.get_store(indent=4)
        self.assertIs(store.data_type, DataPk1)
        self.assertFalse(store.enable_async_backend)
        store.clear()

        data = DataPk1(pk1="test", content="test")
        store.add(data)
        self.assertFalse(store._save_tasks)
        self.assertEqual(store.get_all(), [data])
        self.assertEqual(store.get("test"), data)

        with open(store.path, "rb") as f:
            content = f.read()
        self.assertEqual(from_json(content), [data.model_dump()])
