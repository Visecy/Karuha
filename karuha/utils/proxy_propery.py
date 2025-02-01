from typing import Any, Generic, Optional, TypeVar, Union, overload
from typing_extensions import Self


T = TypeVar("T")


class ProxyProperty(Generic[T]):
    """
    a property that proxies to another property

    usage:
    ```py
    class Foo:
        bar: Any
        baz = ProxyProperty("bar")  # equal to self.bar.baz
    ```
    """

    __slots__ = ["base_attr", "name", "mutable"]

    def __init__(self, base_attr: str, /, name: Optional[str] = None, *, mutable: bool = False) -> None:
        self.base_attr = base_attr
        self.name = name
        self.mutable = mutable

    def __set_name__(self, owner: type, name: str, /) -> None:
        if self.name is None:
            self.name = name

    @overload
    def __get__(self, instance: None, owner: type, /) -> Self: ...

    @overload
    def __get__(self, instance: Any, owner: type, /) -> T: ...

    def __get__(self, instance: Any, owner: type, /) -> Union[Self, T]:
        if instance is None:
            return self
        assert self.name is not None
        base_attr = getattr(instance, self.base_attr)
        return getattr(base_attr, self.name)

    def __set__(self, instance: Any, value: T, /) -> None:
        if not self.mutable:
            raise AttributeError("can't set attribute")
        assert self.name is not None
        base_attr = getattr(instance, self.base_attr)
        setattr(base_attr, self.name, value)
