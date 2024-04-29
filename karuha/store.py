import asyncio
import os
import warnings
from abc import abstractmethod
from collections import deque
from inspect import isabstract
<<<<<<< HEAD
from typing import (Any, ClassVar, Deque, Dict, Generic, Iterable, Iterator, List,
                    Literal, Optional, Set, Tuple, Type, TypeVar, Union, cast,
=======
from typing import (Any, ClassVar, Dict, Generic, Iterable, Iterator, List,
                    Literal, Optional, Tuple, Type, TypeVar, Union, cast,
>>>>>>> 8bc44b3e281f767ad80d1aff465f6ce3d69c4d31
                    overload)
from weakref import WeakKeyDictionary, WeakSet

from aiofiles import open as aio_open
from aiofiles import os as aio_os
from aiofiles import ospath as aio_ospath
from pydantic import (BaseModel, Field, GetCoreSchemaHandler, StrictInt,
                      StrictStr, TypeAdapter, model_validator)
from pydantic_core import CoreSchema, core_schema
from typing_extensions import Annotated, Self, get_args, get_origin

import karuha

try:
    import greenback
except ImportError:  # pragma: no cover
    greenback = None


T = TypeVar("T")

_PkFlagObj = object()
PrimaryKey = Annotated[T, Field(frozen=True), _PkFlagObj]


def is_pk_annotation(annotation: Any) -> bool:
    if not get_origin(annotation) is Annotated:
        return False
    return _PkFlagObj in get_args(annotation)


class DataModel(BaseModel, validate_assignment=True):
    __primary_key__: ClassVar[Optional[Tuple[str, ...]]] = None

    data_store: Annotated[Optional["AbstractDataStore[Self]"], Field(exclude=True)] = None

    def set_data_store(self, store: "AbstractDataStore[Self]", /) -> Self:
        assert (
            self.data_store is None or store is self.data_store
        ), "data store already set"
        self.data_store = store
        return self

    def add(self) -> Self:
        assert self.data_store is not None, "data store not set"
        self.data_store.add(self)
        return self

    def update(self) -> Self:
        if self.data_store is not None:
            self.data_store.update(self)
        return self

    def discard(self) -> Self:
        if self.data_store is not None:
            self.data_store.discard(self)
        return self

    def remove(self) -> Self:
        assert self.data_store is not None
        self.data_store.remove(self)
        return self

    def get_primary_key(self) -> Any:
        assert self.__class__.__primary_key__ is not None, "primary key not defined"
        pk = tuple(getattr(self, key) for key in self.__class__.__primary_key__)
        if len(pk) == 1:
            return pk[0]
        return pk

    @model_validator(mode="after")
    def validate_model_update(self) -> Self:
        self.update()
        return self

    def __init_subclass__(
        cls, *, pk: Optional[Iterable[str]] = None, **kwds: Any
    ) -> None:
        super().__init_subclass__(**kwds)
        if isinstance(pk, str):
            pk = [pk]
        if pk is not None:
            pk = list(pk)
            for name in pk:
                ann = cls.__annotations__.get(name)
                if ann is None:  # pragma: no cover
                    warnings.warn(
                        f"cannot find the annotation for primary key {name}",
                        RuntimeWarning,
                    )
                    continue
                if not is_pk_annotation(ann):
                    cls.__annotations__[name] = PrimaryKey[ann]
        else:
            pk = [
                name
                for name, annotation in cls.__annotations__.items()
                if is_pk_annotation(annotation)
            ]
        
        pk_inherited = []
        for c in cls.__bases__:
            if issubclass(c, DataModel) and c.__primary_key__ is not None:
                pk_inherited.extend(filter(lambda x: x not in pk_inherited, c.__primary_key__))
        if pk:
            pk_inherited.extend(filter(lambda x: x not in pk_inherited, pk))
        cls.__primary_key__ = tuple(pk_inherited) or None


class TopicBoundDataModel(DataModel):
    topic: PrimaryKey[StrictStr]


class UserBoundDataModel(DataModel):
    user_id: PrimaryKey[StrictStr]


class MessageBoundDataModel(TopicBoundDataModel):
    seq_id: PrimaryKey[StrictInt]


DEFAULT_NAME = "data"
T_Data = TypeVar("T_Data", bound=DataModel)


class AbstractDataStore(Generic[T_Data]):
    __slots__ = ["name", "__orig_class__", "_data_type"]
    __orig_bases__: Tuple[Type, ...]

    __store_collection__: ClassVar[Dict[str, Type[Self]]] = {}
    __store_type_var__: ClassVar[TypeVar] = T_Data
    __store_cache__: ClassVar[Dict[str, Self]]
    __store_type__: ClassVar[Type[DataModel]]

    def __init__(self, name: str, *, data_type: Optional[Type[T_Data]] = None) -> None:
        self.name = name
        self._data_type = data_type

    @abstractmethod
    def get(self, key: Any, /, default: Optional[T_Data] = None) -> Optional[T_Data]:
        raise NotImplementedError

    @abstractmethod
    def add(self, data: T_Data, /, *, copy: bool = False) -> None:
        raise NotImplementedError

    @abstractmethod
    def discard(self, data: T_Data, /) -> bool:
        raise NotImplementedError

    def update(self, data: T_Data, /) -> None:
        assert data.data_store is self, "data store mismatch"

    def remove(self, data: T_Data, /) -> None:
        if not self.discard(data):
            raise KeyError(data)

    def clear(self) -> None:
        data = list(self.get_all())
        for i in data:
            self.discard(i)

    @abstractmethod
    def get_all(self) -> Iterable[T_Data]:
        raise NotImplementedError

    @abstractmethod
<<<<<<< HEAD
    def keys(self) -> Iterable[Any]:
        raise NotImplementedError

    def values(self) -> Iterable[T_Data]:
        for key in self.keys():
            yield self[key]

    def items(self) -> Iterable[Tuple[Any, T_Data]]:
=======
    def keys(self) -> Iterator[Any]:
        raise NotImplementedError

    def values(self) -> Iterator[T_Data]:
        for key in self.keys():
            yield self[key]

    def items(self) -> Iterator[Tuple[Any, T_Data]]:
>>>>>>> 8bc44b3e281f767ad80d1aff465f6ce3d69c4d31
        for key in self.keys():
            yield key, self[key]

    @classmethod
    def get_store_class(cls, name: str, /) -> Type[Self]:
        return cls.__store_collection__.get(name, cls)

    @classmethod
    def get_store(cls, name: str = DEFAULT_NAME, /, *args: Any, **kwds: Any) -> Self:
        cache = cls.__store_cache__.get(name)
        if cache is not None:
            return cache
        store = cls(name, *args, **kwds)
        cls.__store_cache__[name] = store
        return store

    @property
    def data_type(self) -> Type[T_Data]:
        if self._data_type is not None:
            return cast(Type[T_Data], self._data_type)
        elif hasattr(self.__class__, "__store_type__"):
            self._data_type = cast(Type[T_Data], self.__class__.__store_type__)
            return self._data_type
        elif hasattr(self, "__orig_class__"):
            typed_cls = self.__orig_class__
            parameters = getattr(get_origin(typed_cls), "__parameters__", ())
            for tv, t in zip(parameters, get_args(typed_cls)):
                if tv == self.__store_type_var__:
                    self._data_type = cast(Type[T_Data], t)
                    return self._data_type
        raise TypeError("data_type not specified")

    def __contains__(self, __key: Any) -> bool:
        if isinstance(__key, DataModel):
            return __key in tuple(self.get_all())
        return self.get(__key) is not None

    def __getitem__(self, __key: Any) -> T_Data:
        data = self.get(__key)
        if data is None:
            raise KeyError(__key)
        return data

    def __delitem__(self, __key: Any) -> None:
        self.remove(self[__key])

    def __iter__(self) -> Iterator[T_Data]:
        yield from self.get_all()

    def __len__(self) -> int:
        return len(tuple(self.get_all()))

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.is_instance_schema(cls)

    def __init_subclass__(
        cls, *, store_type: Optional[str] = None, **kwds: Any
    ) -> None:
        super().__init_subclass__(**kwds)
        if store_type:
            assert not isabstract(cls), "cannot specify store_type for abstract class"
            cls.__store_collection__[store_type] = cls
        if not isabstract(cls):
            cls.__store_cache__ = {}
        if hasattr(cls, "__store_type__"):
            return
        for i in cls.__orig_bases__:
            orig = get_origin(i)
            args = get_args(i)
            params = getattr(orig, "__parameters__", ())
            try:
                type_index = params.index(cls.__store_type_var__)
            except ValueError:
                continue
            type_annotation = args[type_index]
            if isinstance(type_annotation, TypeVar):
                cls.__store_type_var__ = type_annotation
            else:
                cls.__store_type__ = type_annotation
            break


DataModel.model_rebuild()
TopicBoundDataModel.model_rebuild()
UserBoundDataModel.model_rebuild()
MessageBoundDataModel.model_rebuild()


class AbstractCachedDataStore(AbstractDataStore[T_Data]):
    __slots__ = ["_indexd_data", "_data"]

    def __init__(self, name: str, *, data_type: Optional[Type[T_Data]] = None) -> None:
        super().__init__(name, data_type=data_type)
        self._indexd_data: Dict[Any, T_Data] = {}
        self._data: List[T_Data] = []

    @abstractmethod
    def prepare_data(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_data(self) -> None:
        raise NotImplementedError

    def get(
        self, key: Any, /, default: Optional[T_Data] = None, *, sync: bool = True
    ) -> Optional[T_Data]:
        if sync:
            self.prepare_data()
        return self._indexd_data.get(key, default)

    def add(self, data: T_Data, /, *, copy: bool = False, sync: bool = True) -> None:
        if copy:
            data = data.model_copy()
        data.set_data_store(self)
        if data.__primary_key__ is not None:
            self._indexd_data[data.get_primary_key()] = data
        else:
            self._data.append(data)
        if sync:
            self.update_data()

    def update(self, data: T_Data) -> None:
        assert data.data_store is self, "data store mismatch"
        self.update_data()

    def get_all(self, *, sync: bool = True) -> List[T_Data]:
        if sync:
            self.prepare_data()
        return self._data.copy() + list(self._indexd_data.values())

    def discard(self, data: T_Data, /, *, sync: bool = True) -> bool:
        if sync:
            self.prepare_data()
        if data.__primary_key__ is not None:
            ret = self._indexd_data.pop(data.get_primary_key(), None)
            if ret is None:
                return False
        else:
            try:
                self._data.remove(data)
            except ValueError:
                return False
        if sync:
            self.update_data()
        return True

    def remove(self, data: T_Data, /, *, sync: bool = True) -> None:
        if sync:
            self.prepare_data()
        if data.__primary_key__ is not None:
            del self._indexd_data[data.get_primary_key()]
        else:
            self._data.remove(data)
        if sync:
            self.update_data()

    def clear(self, *, sync: bool = True) -> None:
        if sync:
            self.prepare_data()
        self._data.clear()
        self._indexd_data.clear()
        if sync:
            self.update_data()

    def keys(self) -> Iterable[Any]:
        self.prepare_data()
        return self._indexd_data.keys()

    def values(self) -> Iterable[T_Data]:
        self.prepare_data()
        return self._indexd_data.values()

    def items(self) -> Iterable[Tuple[Any, T_Data]]:
        self.prepare_data()
        return self._indexd_data.items()

    def __getitem__(self, __key: Any, /) -> T_Data:
        self.prepare_data()
        return self._indexd_data[__key]

    def __contains__(self, __key: Any, /) -> bool:
        self.prepare_data()
        if isinstance(__key, DataModel):
            if __key.__primary_key__ is not None:
                return __key.get_primary_key() in self._indexd_data
            else:
                return __key in self._data
        return __key in self._indexd_data

    def __iter__(self) -> Iterator[T_Data]:
        self.prepare_data()
        yield from self._data
        yield from self._indexd_data.values()

    def __len__(self) -> int:
        self.prepare_data()
        return len(self._data) + len(self._indexd_data)


class MemoryStore(AbstractCachedDataStore[T_Data], store_type="memory"):
    __slots__ = []

    def prepare_data(self) -> None:
        pass

    def update_data(self) -> None:
        pass


<<<<<<< HEAD
class LruStore(AbstractDataStore[T_Data], store_type="lru"):
    __slots__ = ["_cache", "_index"]

    def __init__(
        self, name: StrictStr, maxlen: int = 128, *, data_type: Optional[Type[T_Data]] = None
    ) -> None:
        super().__init__(name, data_type=data_type)
        self._cache: Deque[T_Data] = deque(maxlen=maxlen)
        self._index: Dict[Any, T_Data] = {}
    
    def get(
        self, key: Any, /, default: Optional[T_Data] = None
    ) -> Optional[T_Data]:
        item = self._index.get(key, default)
        if item is not None:
            self.move_to_end(item)
        return item

    def add(self, data: T_Data, /, *, copy: bool = False) -> None:
        if copy:
            data = data.model_copy()
        if len(self._cache) == self._cache.maxlen:
            old = self._cache[0]
            if old.__primary_key__ is not None:
                del self._index[old.get_primary_key()]
        self._cache.append(data)
        data.set_data_store(self)
        if data.__primary_key__ is not None:
            self._index[data.get_primary_key()] = data
    
    def update(self, data: T_Data) -> None:
        self.move_to_end(data)
    
    def get_all(self) -> List[T_Data]:
        return list(self._cache)
    
    def discard(self, data: T_Data, /) -> bool:
        try:
            self._cache.remove(data)
        except ValueError:
            return False
        if data.__primary_key__ is not None:
            self._index.pop(data.get_primary_key())
        return True
    
    def remove(self, data: T_Data) -> None:
        self._cache.remove(data)
        if data.__primary_key__ is not None:
            del self._index[data.get_primary_key()]
    
    def clear(self) -> None:
        self._cache.clear()
        self._index.clear()
    
    def move_to_end(self, data: T_Data, /) -> None:
        if data not in self._cache:
            raise ValueError("data not in store")
        self._cache.remove(data)
        self._cache.append(data)
    
    def keys(self) -> Iterable[Any]:
        return self._index.keys()
    
    def values(self) -> Iterable[T_Data]:
        return self._index.values()
    
    def items(self) -> Iterable[Tuple[Any, T_Data]]:
        return self._index.items()

    @property
    def maxlen(self) -> StrictInt:
        maxlen = self._cache.maxlen
        assert maxlen is not None
        return maxlen
    
    def __getitem__(self, __key: Any) -> T_Data:
        item = self._index[__key]
        self.move_to_end(item)
        return item
    
    def __contains__(self, __key: Any) -> bool:
        if isinstance(__key, DataModel):
            if __key.__primary_key__ is not None:
                return __key.get_primary_key() in self._index
            else:
                return __key in self._cache
        return __key in self._index

    def __iter__(self) -> Iterator[T_Data]:
        return iter(self._cache)
    
    def __len__(self) -> StrictInt:
        return len(self._cache)


=======
>>>>>>> 8bc44b3e281f767ad80d1aff465f6ce3d69c4d31
class AbstractAsyncCachedStore(AbstractCachedDataStore[T_Data]):
    __slots__ = ["_load_tasks", "_save_tasks", "_wait_list", "_loaded"]

    enable_async_backend: ClassVar[bool] = greenback is not None

    def __init__(
        self, name: StrictStr, *, data_type: Optional[Type[T_Data]] = None
    ) -> None:
        super().__init__(name, data_type=data_type)
        self._load_tasks: WeakSet[asyncio.Task] = WeakSet()
        self._save_tasks: WeakSet[asyncio.Task] = WeakSet()
        self._wait_list: WeakKeyDictionary[asyncio.Task, WeakSet[asyncio.Task]] = (
            WeakKeyDictionary()
        )
        self._loaded = False

        try:
            task = asyncio.current_task()
            if task is not None and greenback is not None:
                # init greenback
                greenback.bestow_portal(task)
            self._loaded = True
            self.load_backend()
        except RuntimeError:
            pass

    @abstractmethod
    async def load(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def save(self) -> None:
        raise NotImplementedError

    def load_backend(self) -> None:
        assert self.enable_async_backend, "async backend task is not enabled"
        self._load_tasks.add(asyncio.create_task(self.load()))

    def save_backend(self) -> None:
        assert self.enable_async_backend, "async backend task is not enabled"
        self._save_tasks.add(asyncio.create_task(self.save()))

    async def wait_tasks(self, *, load: bool = True, save: bool = True) -> None:
        if load:
            await self._wait_tasks(self._load_tasks)
        if save:
            await self._wait_tasks(self._save_tasks)

    def wait_tasks_sync(self, *, load: bool = True, save: bool = True) -> None:
        if not self._should_wait(load=load, save=save):
            return
        assert (
            greenback is not None
        ), "greenback is not installed, please installing it first"
        greenback.await_(self.wait_tasks(load=load, save=save))

    def _should_wait(self, *, load: bool = True, save: bool = True) -> bool:
        return (load and any(not t.done() for t in self._load_tasks)) or (
            save and any(not t.done() for t in self._save_tasks)
        )

    async def _wait_tasks(self, wait_tasks: Iterable[asyncio.Task]) -> None:
        task = asyncio.current_task()
        assert task is not None, "current task is not available"
        mask = {task}
        queue = deque(mask)
        while queue:
            current = queue.popleft()
            if neighbour := self._wait_list.get(current):
                queue.extend(neighbour - mask)
                mask.update(neighbour)

        tasks = []
        for t in wait_tasks:
            if t in mask:
                continue
            tasks.append(t)
            wl = self._wait_list.get(t, WeakSet())
            wl.add(task)
            self._wait_list[t] = wl

        try:
            await asyncio.gather(*tasks)
        finally:
            for wl in self._wait_list.values():
                wl.discard(task)

    def prepare_data(self) -> None:
        if not self._loaded:
            self._loaded = True
            self.load_backend()
        self.wait_tasks_sync(load=True, save=False)

    def update_data(self) -> None:
        self.save_backend()

    @staticmethod
    def async_backend_available() -> bool:
        return greenback is not None and greenback.has_portal()


class AbstractSimpleFileDataStore(AbstractAsyncCachedStore[T_Data]):
    __slots__ = ["path"]

    def __init__(
        self,
        /,
        name: str,
        path_format: str = "data/{name}",
        *,
        data_type: Optional[Type[T_Data]] = None,
    ) -> None:
        super().__init__(name, data_type=data_type)
        self.path = os.path.join(karuha.WORKDIR, self.format_path(path_format))

    @abstractmethod
    def encode_data(self) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def decode_data(self, data: bytes) -> None:
        raise NotImplementedError

    def format_path(self, path: str) -> Union[str, os.PathLike]:
        return path.format(name=self.name)

    async def load(self) -> None:
        if not await aio_ospath.exists(self.path):  # pragma: no cover
            return
        await self.wait_tasks(load=False)
        async with aio_open(self.path, "rb") as f:
            self.decode_data(await f.read())

    async def save(self) -> None:
        await aio_os.makedirs(os.path.dirname(self.path), exist_ok=True)
        await self.wait_tasks(save=False)
        async with aio_open(self.path, "wb") as f:
            await f.write(self.encode_data())

    def load_backend(self) -> None:
        if not self.enable_async_backend:
            self._load_sync()
            return
        super().load_backend()

    def save_backend(self) -> None:
        if not self.enable_async_backend:
            self._save_sync()
            return
        super().save_backend()

    def _load_sync(self) -> None:
        if not os.path.exists(self.path):  # pragma: no cover
            return
        self.wait_tasks_sync()
        with open(self.path, "rb") as f:
            self.decode_data(f.read())

    def _save_sync(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.wait_tasks_sync()
        with open(self.path, "wb") as f:
            f.write(self.encode_data())


class JsonFileStore(AbstractSimpleFileDataStore[T_Data], store_type="json"):
    __slots__ = ["dump_kwds"]

    def __init__(
        self,
        /,
        name: str,
        path_format: str = "data/{name}.json",
        *,
        data_type: Optional[Type[T_Data]] = None,
        **dump_kwds: Any,
    ) -> None:
        self.dump_kwds = dump_kwds
        super().__init__(name, path_format, data_type=data_type)

    def encode_data(self) -> bytes:
        type_adapter = TypeAdapter(List[self.data_type])
        return type_adapter.dump_json(self.get_all(sync=False), **self.dump_kwds)

    def decode_data(self, data: bytes) -> None:
        if not data:  # pragma: no cover
            return
        type_adapter = TypeAdapter(List[self.data_type])
        data_list = cast(List[T_Data], type_adapter.validate_json(data))
        for i in data_list:
            self.add(i, copy=False, sync=False)


@overload
def get_store(
    store_type: Literal["memory"],
    /,
    name: str = ...,
    *args: Any,
    data_type: Optional[Type[T_Data]] = None,
    **kwds: Any,
) -> MemoryStore[T_Data]: ...


@overload
def get_store(
    store_type: Literal["json"],
    /,
    name: str = ...,
    *args: Any,
    data_type: Optional[Type[T_Data]] = None,
    **kwds: Any,
) -> JsonFileStore[T_Data]: ...


@overload
def get_store(
<<<<<<< HEAD
    store_type: Literal["lru"],
    /,
    name: str = ...,
    maxlen: int = ...,
    *args: Any,
    data_type: Optional[Type[T_Data]] = None,
    **kwds: Any,
) -> LruStore[T_Data]: ...


@overload
def get_store(
=======
>>>>>>> 8bc44b3e281f767ad80d1aff465f6ce3d69c4d31
    store_type: str,
    /,
    name: str = ...,
    *args: Any,
    data_type: Optional[Type[T_Data]] = None,
    **kwds: Any,
) -> AbstractDataStore[T_Data]: ...


def get_store(
    store_type: str,
    /,
    name: str = DEFAULT_NAME,
    *args: Any,
    data_type: Optional[Type[T_Data]] = None,
    **kwds: Any,
) -> AbstractDataStore[T_Data]:
    return AbstractDataStore.__store_collection__[store_type].get_store(
        name, *args, data_type=data_type, **kwds
    )
