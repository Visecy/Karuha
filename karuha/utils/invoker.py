from abc import ABC, abstractmethod
from dataclasses import is_dataclass
from inspect import Parameter, Signature, isclass
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
    def get_dependency(self, param: Parameter, /, **kwds: Any) -> Any:
        raise NotImplementedError

    def validate_dependency(self, param: Parameter, val: Any, /, **kwds: Any) -> Any:
        if param.annotation is param.empty:
            return val
        ann = param.annotation
        context = {"name": param.name, "param": param, "annotation": param.annotation, **kwds}
        config: Optional[ConfigDict] = None if _type_has_config(ann) else {"arbitrary_types_allowed": True}
        try:
            return TypeAdapter(ann, config=config).validate_python(val, context=context)
        except Exception as e:
            raise KaruhaHandlerInvokerError(
                f"failed to validate dependency '{param.name}':\n{e}"
            ) from e

    def resolve_missing_dependencies(
        self, missing: Dict[Parameter, KaruhaHandlerInvokerError], /, **kwds: Any
    ) -> Dict[str, Any]:
        result = {}
        still_missing = {}

        # resolve dependency class & instance
        for param in missing:
            param_type = get_origin(param.annotation)
            if param_type is Annotated:
                for i in get_args(param.annotation):
                    if isinstance(i, HandlerInvokerDependency) or isclass(i) and issubclass(i, HandlerInvokerDependency):
                        param_type = i
                        break
                else:  # pragma: no cover
                    still_missing[param] = missing[param]
                    continue
            try:
                if isclass(param_type) and issubclass(param_type, HandlerInvokerDependency):
                    ret = param_type.resolve_dependency(self, param, **kwds)
                elif isinstance(param_type, HandlerInvokerDependency):
                    ret = param_type.resolve_dependency(self, param, dependency_instance=i, **kwds)
                else:
                    raise missing[param]
                result[param.name] = self.validate_dependency(param, ret, **kwds)
            except KaruhaHandlerInvokerError as e:
                still_missing[param] = e
            except Exception as e:  # pragma: no cover
                err = KaruhaHandlerInvokerError(
                    f"failed to resolve dependency '{param.name}':\n{e}"
                )
                err.__suppress_context__ = True
                err.__cause__ = e
                still_missing[param] = err

        # fill defaults
        for param in list(still_missing.keys()):
            if param.default is not param.empty:
                result[param.name] = param.default
                still_missing.pop(param)

        if not still_missing:
            return result
        raise KaruhaHandlerInvokerError(
            f"Missing dependencies: (extra data: {kwds})\n" +
            ''.join(
                f"\t{param.name}: {error}\t"
                for param, error in still_missing.items()
            )
        )

    def extract_handler_params(self, sig: Signature, *, name: Optional[str] = None) -> Tuple[list, Dict[str, Any]]:
        dependencies = {}
        missing = {}
        kwds = {"signature": sig, "identifier": name}
        for param in sig.parameters.values():
            try:
                val = self.get_dependency(param, **kwds)
            except KaruhaHandlerInvokerError as e:
                missing[param] = e
            else:
                dependencies[param.name] = val

        dependencies.update(self.resolve_missing_dependencies(missing, **kwds))
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
        args, kwargs = self.extract_handler_params(Signature.from_callable(handler), name=getattr(handler, "__name__", None))
        return handler(*args, **kwargs)


class HandlerInvokerDependency(ABC):
    __slots__ = []

    @classmethod
    @abstractmethod
    def resolve_dependency(cls, invoker: AbstractHandlerInvoker, param: Parameter, **kwds: Any) -> Any:
        raise NotImplementedError


class HandlerInvokerModel(AbstractHandlerInvoker, BaseModel):
    __slots__ = []

    def get_dependency(self, param: Parameter, /, **kwds: Any) -> Any:
        if param.name not in self.model_fields_set.union(self.model_computed_fields):
            raise KaruhaHandlerInvokerError(f"dependency '{param.name}' is not in the model")
        try:
            val = getattr(self, param.name)
        except AttributeError as e:  # pragma: no cover
            raise KaruhaHandlerInvokerError(f"failed to get dependency '{param.name}'") from e
        return self.validate_dependency(param, val, **kwds)


_DEPENDENCY_FLAG = object()

Dependency = Annotated[T, _DEPENDENCY_FLAG]
depend_property: Type[property] = new_class("depend_property", (property,))


def is_depend_annotation(annotation: Any) -> bool:
    if get_origin(annotation) is not Annotated:
        return False
    return _DEPENDENCY_FLAG in get_args(annotation)


class HandlerInvoker(AbstractHandlerInvoker):
    __slots__ = []

    __dependencies__: ClassVar[Dict[str, Callable[[Self, Parameter], Any]]] = {}

    def get_dependency(self, param: Parameter, /, **kwds: Any) -> Any:
        try:
            val = self.__dependencies__[param.name](self, param)
        except KeyError:  # pragma: no cover
            raise KaruhaHandlerInvokerError(f"failed to get dependency '{param.name}'") from None
        return self.validate_dependency(param, val, **kwds)

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
