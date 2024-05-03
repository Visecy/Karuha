from abc import ABC, abstractmethod
from dataclasses import is_dataclass
from inspect import Parameter, Signature
from types import new_class
from typing import Any, Callable, ClassVar, Dict, Optional, Tuple, Type, TypeVar
from typing_extensions import Annotated, Self, get_args, get_origin, is_typeddict

from pydantic import BaseModel, ConfigDict, TypeAdapter

from ..exception import KaruhaHandlerInvokerError


T = TypeVar("T")


def _type_has_config(type_: Any) -> bool:
    """Returns whether the type has config."""
    try:
        return issubclass(type_, BaseModel) or is_dataclass(type_) or is_typeddict(type_)
    except TypeError:
        # type is not a class
        return False


class AbstractHandlerInvoker(ABC):
    __slots__ = []

    @abstractmethod
    def get_dependency(self, param: Parameter) -> Any:
        raise NotImplementedError
    
    def validate_dependency(self, param: Parameter, val: Any) -> Any:
        if param.annotation is param.empty:
            return val
        ann = param.annotation
        context = {"name": param.name, "param": param, "annotation": param.annotation}
        if _type_has_config(ann):
            config: Optional[ConfigDict] = None
        else:
            config = {"arbitrary_types_allowed": True}

        try:
            return TypeAdapter(ann, config=config).validate_python(val, context=context)
        except Exception as e:
            raise KaruhaHandlerInvokerError(
                f"failed to validate dependency '{param.name}':\n{e}"
            ) from e

    def resolve_missing_dependencies(self, missing: Dict[Parameter, KaruhaHandlerInvokerError]) -> Dict[str, Any]:
        if not missing:
            return {}
        raise KaruhaHandlerInvokerError(
            "Missing dependencies:\n" +
            ''.join(
                f"\t{param.name}: {error}\t"
                for param, error in missing.items()
            )
        )

    def extract_handler_params(self, sig: Signature) -> Tuple[list, Dict[str, Any]]:
        dependencies = {}
        missing = {}
        for param in sig.parameters.values():
            try:
                val = self.get_dependency(param)
            except KaruhaHandlerInvokerError as e:
                if param.default is not param.empty:
                    dependencies[param.name] = param.default
                else:
                    missing[param] = e
            else:
                dependencies[param.name] = val

        dependencies.update(self.resolve_missing_dependencies(missing))
        assert len(dependencies) == len(sig.parameters)
        args = []
        kwargs = {}
        for param in sig.parameters.values():
            if param.kind in [Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD]:
                raise KaruhaHandlerInvokerError(f"{param.kind} parameters are not supported")
            elif param.kind == Parameter.POSITIONAL_ONLY:
                args.append(dependencies[param.name])
            else:
                kwargs[param.name] = dependencies[param.name]
        return args, kwargs

    def call_handler(self, handler: Callable[..., T]) -> T:
        args, kwargs = self.extract_handler_params(Signature.from_callable(handler))
        return handler(*args, **kwargs)


class HandlerInvokerModel(AbstractHandlerInvoker, BaseModel):
    __slots__ = []

    def get_dependency(self, param: Parameter) -> Any:
        if param.name not in self.model_fields_set.union(self.model_computed_fields):
            raise KaruhaHandlerInvokerError(f"dependency '{param.name}' is not in the model")
        try:
            val = getattr(self, param.name)
        except AttributeError as e:  # pragma: no cover
            raise KaruhaHandlerInvokerError(f"failed to get dependency '{param.name}'") from e
        return self.validate_dependency(param, val)


_DEPENDENCY_FLAG = object()

Dependency = Annotated[T, _DEPENDENCY_FLAG]
depend_property: Type[property] = new_class("depend_property", (property,))


def is_depend_annotation(annotation: Any) -> bool:
    if not get_origin(annotation) is Annotated:
        return False
    return _DEPENDENCY_FLAG in get_args(annotation)


class HandlerInvoker(AbstractHandlerInvoker):
    __slots__ = []

    __dependencies__: ClassVar[Dict[str, Callable[[Self, Parameter], Any]]] = {}

    def get_dependency(self, param: Parameter) -> Any:
        try:
            val = self.__dependencies__[param.name](self, param)
        except KeyError:  # pragma: no cover
            raise KaruhaHandlerInvokerError(f"failed to get dependency '{param.name}'") from None
        return self.validate_dependency(param, val)

    @classmethod
    def register_dependency(cls, name: str, getter: Callable[[Self, Parameter], Any]) -> None:
        cls.__dependencies__[name] = getter
    
    def __init_subclass__(cls, **kwds: Any) -> None:
        cls.__dependencies__ = cls.__dependencies__.copy()
        for name, annotation in cls.__annotations__.items():
            if is_depend_annotation(annotation):
                cls.register_dependency(name, lambda self, param: getattr(self, param.name))
        for name, attr in cls.__dict__.items():
            if isinstance(attr, depend_property):
                cls.register_dependency(name, lambda self, param: getattr(self, param.name))
        super().__init_subclass__(**kwds)
