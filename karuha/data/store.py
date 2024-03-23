import asyncio
import os
import warnings
from abc import abstractmethod
from inspect import isabstract, isclass
from typing import (Any, ClassVar, Dict, FrozenSet, Generic, Iterable,
                    Iterator, List, Literal, Optional, Tuple, Type, TypeVar,
                    Union, cast, overload)
from weakref import WeakSet

from aiofiles import open as aio_open
from aiofiles import os as aio_os
from aiofiles import ospath as aio_ospath
from pydantic import (BaseModel, Field, GetCoreSchemaHandler, StrictInt, StrictStr, TypeAdapter,
                      model_validator)
from pydantic_core import CoreSchema, core_schema
from typing_extensions import Annotated, Self, get_args, get_origin

import karuha

try:
    import greenback
except ImportError:
    greenback = None


T = TypeVar("T")

_PkFlagObj = object()
PrimaryKey = Annotated[T, Field(frozen=True), _PkFlagObj]


def is_pk_annotation(annotation: Any) -> bool:
    if not get_origin(annotation) is Annotated:
        return False
    return _PkFlagObj in get_args(annotation)


class DataModel(BaseModel, validate_assignment=True):
    __primary_key__: ClassVar[Optional[FrozenSet[str]]] = None

    data_store: Annotated[Optional["AbstractDataStore"], Field(exclude=True)] = None

    def set_data_store(self, store: "AbstractDataStore", /) -> Self:
        assert self.data_store is None or store is self.data_store, "data store already set"
        self.data_store = store
        return self
    
    def update(self) -> Self:
        if self.data_store is not None:
            self.data_store.update(self)
        return self
    
    def get_primary_key(self) -> Any:
        assert self.__primary_key__, "primary key not defined"
        pk = tuple(getattr(self, key) for key in self.__primary_key__)
        if len(pk) == 1:
            return pk[0]
        return pk

    @model_validator(mode="after")
    def validate_model_update(self) -> Self:
        self.update()
        return self

    def __init_subclass__(cls, *, pk: Optional[Iterable[str]] = None, **kwds: Any) -> None:
        super().__init_subclass__(**kwds)
        if isinstance(pk, str):
            pk = [pk]
        elif pk is not None:
            pk = list(pk)
            for name in pk:
                ann = cls.__annotations__.get(name)
                if ann is None:  # pragma: no cover
                    warnings.warn(f"cannot find the annotation for primary key {name}", RuntimeWarning)
                    continue
                if not is_pk_annotation(ann):
                    cls.__annotations__[name] = PrimaryKey[ann]
        else:
            pk = [name for name, annotation in cls.__annotations__.items() if is_pk_annotation(annotation)]

        if not pk:
            return
        if cls.__primary_key__ is None:
            cls.__primary_key__ = frozenset(pk)
        else:
            cls.__primary_key__ = cls.__primary_key__.union(pk)


class TopicBoundDataModel(DataModel):
    topic: PrimaryKey[StrictStr]


class UserBoundDataModel(DataModel):
    user_id: PrimaryKey[StrictStr]


class MessageBoundDataModel(TopicBoundDataModel):
    seq_id: PrimaryKey[StrictInt]


T_Data = TypeVar("T_Data", bound=DataModel)


class AbstractDataStore(Generic[T_Data]):
    __slots__ = ["name", "__orig_class__", "_data_type"]
    __orig_bases__: ClassVar[Tuple[Type]]
    __store_collection__: ClassVar[Dict[str, Type[Self]]] = {}
    __store_cache__: ClassVar[Dict[str, Self]] = {}
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
    def keys(self) -> Iterator[Any]:
        raise NotImplementedError

    def values(self) -> Iterator[T_Data]:
        for key in self.keys():
            yield self[key]

    def items(self) -> Iterator[Tuple[Any, T_Data]]:
        for key in self.keys():
            yield key, self[key]

    @classmethod
    def get_store_class(cls, name: str, /) -> Type[Self]:
        return cls.__store_collection__.get(name, cls)

    @classmethod
    def get_store(cls, name: str = '', /, *args: Any, **kwds: Any) -> Self:
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
        elif hasattr(self, "__orig_class__"):
            self._data_type, = get_args(self.__orig_class__)
            return self._data_type
        elif hasattr(self.__class__, "__store_type__"):
            self._data_type = cast(Type[T_Data], self.__store_type__)
            return self._data_type
        else:
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
        cls.__store_cache__ = {}
        for i in cls.__orig_bases__:
            orig = get_origin(i)
            args = get_args(i)
            if (
                isclass(orig)
                and issubclass(orig, AbstractDataStore)
                and len(args) == 1
                and not isinstance(args[0], TypeVar)
            ):
                cls.__store_type__ = args[0]
                break
        if store_type:
            assert not isabstract(cls)
            cls.__store_collection__[store_type] = cls


DataModel.model_rebuild()


class _CachedDataStore(AbstractDataStore[T_Data]):
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
    
    def get(self, key: Any, /, default: Optional[T_Data] = None) -> Optional[T_Data]:
        self.prepare_data()
        return self._indexd_data.get(key, default)
    
    def add(self, data: T_Data, /, *, copy: bool = False) -> None:
        if copy:
            data = data.model_copy()
        data.set_data_store(self)
        if data.__primary_key__ is not None:
            self._indexd_data[data.get_primary_key()] = data
        else:
            self._data.append(data)
        self.update_data()
    
    def update(self, data: T_Data) -> None:
        assert data.data_store is self, "data store mismatch"
        self.update_data()
    
    def get_all(self) -> List[T_Data]:
        self.prepare_data()
        return self._data.copy() + list(self._indexd_data.values())
    
    def discard(self, data: T_Data, /) -> bool:
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
        self.update_data()
        return True
    
    def remove(self, data: T_Data) -> None:
        self.prepare_data()
        if data.__primary_key__ is not None:
            del self._indexd_data[data.get_primary_key()]
        else:
            self._data.remove(data)
        self.update_data()
    
    def clear(self) -> None:
        self.prepare_data()
        self._data.clear()
        self._indexd_data.clear()
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


class MemoryStore(_CachedDataStore[T_Data], store_type="memory"):
    __slots__ = []

    def prepare_data(self) -> None:
        pass

    def update_data(self) -> None:
        pass


class AbstractSimpleFileDataStore(_CachedDataStore[T_Data]):
    __slots__ = ["path", "_load_tasks", "_save_tasks"]

    enable_async_backend: ClassVar[bool] = greenback is not None

    def __init__(self, /, name: str, path_format: str = "data/{name}", *, data_type: Optional[Type[T_Data]] = None) -> None:
        super().__init__(name, data_type=data_type)
        self.path = os.path.join(karuha.WORKDIR, self.format_path(path_format))
        self._load_tasks = WeakSet()
        self._save_tasks = WeakSet()

        try:
            task = asyncio.current_task()
            if task is not None and greenback is not None:
                # init greenback
                greenback.bestow_portal(task)
        except RuntimeError:
            pass
        self.load_backend()

    @abstractmethod
    def encode_data(self) -> bytes:
        raise NotImplementedError
    
    @abstractmethod
    def decode_data(self, data: bytes) -> None:
        raise NotImplementedError
    
    def format_path(self, path: str) -> Union[str, os.PathLike]:
        return path.format(name=self.name)
    
    async def load(self) -> None:
        if not await aio_ospath.exists(self.path):
            return
        await self.wait_tasks()
        async with aio_open(self.path, "rb") as f:
            self.decode_data(await f.read())
    
    async def save(self) -> None:
        await aio_os.makedirs(os.path.dirname(self.path), exist_ok=True)
        await self.wait_tasks()
        async with aio_open(self.path, "wb") as f:
            await f.write(self.encode_data())
    
    def load_backend(self) -> None:
        if not self.enable_async_backend:
            self._load_sync()
            return
        self._load_tasks.add(asyncio.create_task(self.load()))
    
    def save_backend(self) -> None:
        if not self.enable_async_backend:
            self._save_sync()
            return
        self._save_tasks.add(asyncio.create_task(self.save()))
    
    def _load_sync(self) -> None:
        if not os.path.exists(self.path):
            return
        self.wait_tasks_sync()
        with open(self.path, "rb") as f:
            self.decode_data(f.read())
    
    def _save_sync(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.wait_tasks_sync()
        with open(self.path, "wb") as f:
            f.write(self.encode_data())
    
    async def wait_tasks(self, *, load: bool = True, save: bool = True) -> None:
        task = asyncio.current_task()
        task_type = None
        if task is not None:
            if task in self._load_tasks:
                task_type = "load"
                self._load_tasks.remove(task)
            elif task in self._save_tasks:
                task_type = "save"
                self._save_tasks.remove(task)
        try:
            if load:
                await asyncio.gather(*self._load_tasks)
            if save:
                await asyncio.gather(*self._save_tasks)
        except:
            if task_type == "load":
                self._load_tasks.add(task)
            elif task_type == "save":
                self._save_tasks.add(task)
            raise
    
    def wait_tasks_sync(self, *, load: bool = True, save: bool = True) -> None:
        if not ((save and self._save_tasks) or (load and self._load_tasks)):
            return
        assert greenback is not None, "greenback is not installed, please installing it first"
        greenback.await_(self.wait_tasks(load=load, save=save))
    
    def prepare_data(self) -> None:
        self.wait_tasks_sync(load=True, save=False)
    
    def update_data(self) -> None:
        self.save_backend()
    
    @classmethod
    def async_backend_available(cls) -> bool:
        return greenback is not None and cls.enable_async_backend and greenback.has_portal()


class JsonFileStore(AbstractSimpleFileDataStore[T_Data], store_type="json"):
    __slots__ = []
    
    def __init__(self, /, name: str, path_format: str = "data/{name}.json", *, data_type: Optional[Type[T_Data]] = None) -> None:
        super().__init__(name, path_format, data_type=data_type)

    def encode_data(self) -> bytes:
        type_adapter = TypeAdapter(List[self.data_type])
        return type_adapter.dump_json(self.get_all(), indent=4)

    def decode_data(self, data: bytes) -> None:
        type_adapter = TypeAdapter(List[self.data_type])
        data_list = cast(List[T_Data], type_adapter.validate_json(data))
        for i in data_list:
            self.add(i)


@overload
def get_store(store_type: Literal["memory"], /, name: str = '', *args: Any, data_type: Optional[Type[T_Data]] = None, **kwds: Any) -> MemoryStore[T_Data]:
    ...


@overload
def get_store(store_type: Literal["json"], /, name: str = '', *args: Any, data_type: Optional[Type[T_Data]] = None, **kwds: Any) -> JsonFileStore[T_Data]:
    ...


@overload
def get_store(store_type: str, /, name: str = '', *args: Any, data_type: Optional[Type[T_Data]] = None, **kwds: Any) -> AbstractDataStore[T_Data]:
    ...


def get_store(store_type: str, /, name: str = '', *args: Any, data_type: Optional[Type[T_Data]] = None, **kwds: Any) -> AbstractDataStore[T_Data]:
    return AbstractDataStore.__store_collection__[store_type].get_store(name, *args, data_type=data_type, **kwds)
