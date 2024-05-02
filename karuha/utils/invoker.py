from abc import ABC, abstractmethod
from inspect import Parameter, Signature
from typing import Any, Callable, Dict, Tuple

from pydantic import BaseModel, TypeAdapter

from ..exception import KaruhaHandlerInvokerError


class AnstractHandlerInvoker(ABC):
    __slots__ = []

    @abstractmethod
    def get_dependency(self, param: Parameter) -> Any:
        raise NotImplementedError
    
    def resolve_missing_dependencies(self, missing: Dict[Parameter, KaruhaHandlerInvokerError]) -> Dict[str, Any]:
        raise KaruhaHandlerInvokerError(
            "Missing dependencies:\n" +
            ''.join(
                f"\t{param.name}: {error}\t"
                for param, error in missing.items()
            )
        )

    def get_handler_params(self, sig: Signature) -> Tuple[list, Dict[str, Any]]:
        dependencies = {}
        missing = {}
        for param in sig.parameters.values():
            try:
                val = self.get_dependency(param)
            except KaruhaHandlerInvokerError as e:
                missing[param] = e
            else:
                dependencies[param.name] = val
        dependencies.update(self.resolve_missing_dependencies(missing))
        assert len(dependencies) == len(sig.parameters)
        args = []
        kwargs = {}
        for param in sig.parameters.values():
            if param.kind == Parameter.POSITIONAL_ONLY:
                args.append(dependencies[param.name])
            else:
                kwargs[param.name] = dependencies[param.name]
        return args, kwargs

    def call_handler(self, handler: Callable[..., Any]) -> Any:
        args, kwargs = self.get_handler_params(Signature.from_callable(handler))
        return handler(*args, **kwargs)


class HandlerInvokerModel(AnstractHandlerInvoker, BaseModel):
    __slots__ = []

    def get_dependency(self, param: Parameter) -> Any:
        try:
            val = getattr(self, param.name)
        except AttributeError as e:
            if param.default is not param.empty:
                return param.default
            raise KaruhaHandlerInvokerError(f"failed to get dependency {param.name}") from e
        return self.validate_dependency(param, val)
    
    def validate_dependency(self, param: Parameter, val: Any) -> Any:
        if param.annotation is param.empty:
            return val
        context = {"name": param.name, "param": param, "annotation": param.annotation}
        try:
            return TypeAdapter(param.annotation).validate_python(val, context=context)
        except Exception as e:
            if param.default is param.empty:
                raise KaruhaHandlerInvokerError(f"failed to validate dependency {param.name}") from e
            return param.default
