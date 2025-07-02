import asyncio
import warnings
from abc import abstractmethod
from collections import deque
from inspect import Parameter, isabstract
from typing import (
    Any,
    AsyncIterable,
    ClassVar,
    Deque,
    Dict,
    Generic,
    Iterable,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
    cast,
)

from pydantic import BaseModel, Field, StrictStr
from typing_extensions import Annotated, Self, get_args, get_origin

from .invoker import AbstractHandlerInvoker, HandlerInvokerDependency


T = TypeVar("T")

_PkFlagObj = object()
PrimaryKey = Annotated[T, Field(frozen=True), _PkFlagObj]


def is_pk_annotation(annotation: Any) -> bool:
    if get_origin(annotation) is not Annotated:
        return False
    return _PkFlagObj in get_args(annotation)


class DataModel(BaseModel, validate_assignment=True):
    __primary_key__: ClassVar[Optional[Tuple[str, ...]]] = None

    def get_primary_key(self) -> Any:
        assert self.__class__.__primary_key__ is not None, "primary key not defined"
        pk = tuple(getattr(self, key) for key in self.__class__.__primary_key__)
        return pk[0] if len(pk) == 1 else pk

    def __init_subclass__(cls, *, pk: Optional[Iterable[str]] = None, **kwds: Any) -> None:
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
            pk = [name for name, annotation in cls.__annotations__.items() if is_pk_annotation(annotation)]

        pk_inherited = []
        for c in cls.__bases__:
            if issubclass(c, DataModel) and c.__primary_key__ is not None:
                pk_inherited.extend(filter(lambda x: x not in pk_inherited, c.__primary_key__))
        if pk:
            pk_inherited.extend(filter(lambda x: x not in pk_inherited, pk))
        cls.__primary_key__ = tuple(pk_inherited) or None


DEFAULT_NAME = "data"
T_Data = TypeVar("T_Data", bound=DataModel)


class AbstractModelDB(HandlerInvokerDependency, Generic[T_Data]):
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
    def set(self, data: T_Data, /, copy: bool = False) -> None:
        raise NotImplementedError
    
    @abstractmethod
    def remove(self, key_or_model: Any, /) -> bool:
        raise NotImplementedError
    
    @abstractmethod
    def all(self) -> Iterable[T_Data]:
        raise NotImplementedError
    
    @abstractmethod
    def purge(self) -> None:
        raise NotImplementedError

    def save(self) -> None:
        pass

    def close(self) -> None:
        self.save()

    @classmethod
    def resolve_dependency(cls, /, invoker: AbstractHandlerInvoker, param: Parameter, **kwds: Any) -> Any:
        identifier = kwds.get("identifier", None)
        name = f"dependency-{param.name}" if identifier is None else f"dependency-{identifier}-{param.name}"
        data_type = getattr(cls, "__store_type__", None)
        if data_type is None:
            args = get_args(param.annotation)
            parameters = getattr(cls, "__parameters__", ())
            for tv, t in zip(parameters, args):
                if tv == cls.__store_type_var__:
                    data_type = t
                    break
        return cls.get_store(name, data_type=data_type)

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

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def __init_subclass__(cls, *, store_type: Optional[str] = None, **kwds: Any) -> None:
        super().__init_subclass__(**kwds)
        if store_type:
            assert not isabstract(cls), "cannot specify store_type for abstract class"
            cls.__store_collection__[store_type] = cls
        if not isabstract(cls):
            cls.__store_cache__ = {}
        if hasattr(cls, "__store_type__"):
            return
        for i in cls.__orig_bases__:
            orig = get_origin(i) or i
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


class AbstractAsyncModelDB(AbstractModelDB[T_Data], Generic[T_Data]):
    __slots__ = ["_lock"]

    def __init__(self, name: str, *, data_type: Optional[Type[T_Data]] = None) -> None:
        super().__init__(name, data_type=data_type)
        self._lock = asyncio.Lock()
    
    @abstractmethod
    async def get(self, key: Any, /, default: Optional[T_Data] = None) -> Optional[T_Data]:
        raise NotImplementedError

    @abstractmethod
    async def set(self, data: T_Data, /) -> None:
        raise NotImplementedError

    @abstractmethod
    async def remove(self, key_or_model: Any, /) -> bool:
        raise NotImplementedError

    @abstractmethod
    def all(self) -> AsyncIterable[T_Data]:
        raise NotImplementedError

    @abstractmethod
    async def purge(self) -> None:
        raise NotImplementedError

    async def save(self) -> None:
        pass

    async def close(self) -> None:
        await self.save()

    __enter__ = None  # type: ignore
    __exit__ = None  # type: ignore

    async def __aenter__(self) -> Self:
        return self
    
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()


class _BaseCachedModelDB(AbstractModelDB[T_Data], Generic[T_Data]):
    __slots__ = ["_indexd_data", "_data"]

    def __init__(self, name: str, *, data_type: Optional[Type[T_Data]] = None) -> None:
        super().__init__(name, data_type=data_type)
        self._indexd_data: Dict[Any, T_Data] = {}
        self._data: List[T_Data] = []

    def get(self, key: Any, /, default: Optional[T_Data] = None) -> Optional[T_Data]:
        return self._indexd_data.get(key, default)

    def set(self, data: T_Data, /, copy: bool = False) -> None:
        if copy:
            data = data.model_copy()
        if data.__primary_key__ is not None:
            key = data.get_primary_key()
            self._indexd_data[key] = data
        else:
            self._data.append(data)
    
    def remove(self, key_or_model: Any, /) -> bool:
        if isinstance(key_or_model, DataModel):
            if key_or_model.__primary_key__ is None:
                self._data.remove(key_or_model)  # type: ignore
                return True
        else:
            key = key_or_model
        if key in self._indexd_data:
            self._indexd_data.pop(key)
            return True
        return False
    
    def all(self) -> List[T_Data]:
        return self._data + list(self._indexd_data.values())
    
    def purge(self) -> None:
        self._indexd_data.clear()
        self._data.clear()


class MemoryModelDB(_BaseCachedModelDB[T_Data], store_type="memory"):
    __slots__ = []


class LruModelDB(_BaseCachedModelDB[T_Data], store_type="lru"):
    __slots__ = ["_cache", "_index"]

    def __init__(self, name: StrictStr, maxlen: int = 128, *, data_type: Optional[Type[T_Data]] = None) -> None:
        super().__init__(name, data_type=data_type)
        self._cache: Deque[T_Data] = deque(maxlen=maxlen)
        self._index: Dict[Any, T_Data] = {}
    
    def get(self, key: Any, /, default: Optional[T_Data] = None) -> Optional[T_Data]:
        item = self._index.get(key, default)
        if item is not None:
            self.move_to_end(item)
        return item
    
    def set(self, data: T_Data, /, copy: bool = False) -> None:
        if copy:
            data = data.model_copy()
        if data.__primary_key__ is not None:
            key = data.get_primary_key()
            self._index[key] = data
        else:
            self._data.append(data)
        self._cache.append(data)

    def move_to_end(self, data: T_Data, /) -> bool:
        if data not in self._cache:
            return False
        self._cache.remove(data)
        self._cache.append(data)
        return True


class _BaseAsyncCachedModelDB(AbstractAsyncModelDB[T_Data], _BaseCachedModelDB[T_Data]):
    __slots__ = []
    
    async def get(self, key: Any, /, default: Optional[T_Data] = None) -> Optional[T_Data]:
        return super(AbstractAsyncModelDB, self).get(key, default=default)

    async def set(self, data: T_Data, /, copy: bool = False) -> None:
        return super(AbstractAsyncModelDB, self).set(data, copy=copy)

    async def remove(self, key_or_model: Any, /) -> bool:
        return super(AbstractAsyncModelDB, self).remove(key_or_model)

    async def all(self) -> Iterable[T_Data]:
        return super(AbstractAsyncModelDB, self).all()
    
    async def purge(self) -> None:
        return super(AbstractAsyncModelDB, self).purge()
