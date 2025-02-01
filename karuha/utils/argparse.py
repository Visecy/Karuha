import asyncio
from argparse import Action
from argparse import ArgumentParser as _ArgumentParser
from argparse import FileType
from functools import partial
from inspect import Parameter, Signature, signature
from types import MethodType
from typing import TYPE_CHECKING, Any, Callable, Iterable, Literal, Mapping, NoReturn, Optional, Tuple, Type, TypeVar, Union
from weakref import WeakSet

from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema
from typing_extensions import Annotated, Self, get_args, get_origin, get_type_hints

from .invoker import EMPTY, HandlerInvoker

from ..exception import KaruhaCommandCanceledError
from ..logger import logger
from ..session import BaseSession


class ArgumentParser(_ArgumentParser):
    """
    Custom ArgumentParser class that integrates with Karuha's session management.

    :param session: The session object associated with the parser.
    :type session: BaseSession
    :param args: Positional arguments to pass to the superclass constructor.
    :param kwargs: Keyword arguments to pass to the superclass constructor.
    """

    __slots__ = ["session", "tasks"]

    def __init__(self, session: BaseSession, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = session
        self.tasks = WeakSet()

    def _print_message(self, message: str, file: Any = None) -> None:
        """
        Prints a message by sending it through the session.

        :param message: The message to be sent.
        :type message: str
        :param file: The file object to write the message to (unused).
        :type file: Any
        """
        task = asyncio.create_task(self.session.send(message))
        self.tasks.add(task)

    def exit(self, status: int = 0, message: Optional[str] = None) -> NoReturn:
        """
        Exits the argument parsing process by raising a KaruhaCommandCanceledError.

        :param status: The exit status code.
        :type status: int
        :param message: An optional message to be printed before exiting.
        :type message: Optional[str]
        """
        if message:
            self._print_message(message)
        raise KaruhaCommandCanceledError(status)

    async def wait_tasks(self) -> None:
        """
        Waits for all asynchronous tasks to complete.
        """
        await asyncio.gather(*self.tasks)


class _CoreSchemaGetter:
    def __init__(self, func: Callable[[Any, Type, GetCoreSchemaHandler], core_schema.CoreSchema]) -> None:
        self.__func__ = func

    def __get__(self, instance: Any, owner: Any) -> Callable[[Type, GetCoreSchemaHandler], core_schema.CoreSchema]:
        if instance is None:
            instance = owner()
        return MethodType(self.__func__, instance)


class Argument:
    """
    Represents a command-line argument to be added to an ArgumentParser.

    This class allows defining argparse arguments in a declarative way, either directly
    or through type annotations using `Annotated` (aliased as `Arg` for convenience).

    :param args: Positional arguments for the argument.
    :param kwargs: Keyword arguments for the argument.

    Usage:
        >>> version: Arg[
        ...     str,
        ...     "-v", "--version",
        ...     {"action": "version", "version": "0.1.0"}
        ... ]
        # Or using Annotated
        >>> version: Annotated[
        ...     str,
        ...     Argument(
        ...         "-v", "--version",
        ...         action="version",
        ...         version="0.1.0"
        ...     )
        ... ]
    """

    __slots__ = ["args", "kwargs", "dest"]

    if TYPE_CHECKING:

        def __init__(
            self,
            *name_or_flags: str,
            action: Union[str, Type[Action]] = ...,
            nargs: Union[int, str, None] = None,
            const: Any = ...,
            default: Any = ...,
            type: Union[Callable[[str], Any], FileType, str] = ...,
            choices: Iterable[Any] = ...,
            required: bool = ...,
            help: Optional[str] = ...,
            metavar: Union[str, Tuple[str, ...], None] = ...,
            dest: Optional[str] = ...,
            version: str = ...,
            **kwargs: Any,
        ) -> None: ...
    else:

        def __init__(self, *args, **kwds) -> None:
            self.args = args
            self.kwargs = kwds

    def set_name(self, /, name: str, *, keyword: bool = False) -> None:
        """
        Sets the name of the argument.

        :param name: The name to set for the argument.
        :type name: str
        """
        if not self.args:
            self.args = (f"--{name}",) if keyword else (name,)
        if not keyword:
            return
        if "dest" in self.kwargs and self.kwargs["dest"] != name:  # pragma: no cover
            logger.warning("dest is overwritten")
        self.kwargs["dest"] = name

    def set_default(self, /, default: Any) -> None:
        """
        Sets the default value of the argument.

        :param default: The default value to set for the argument.
        :type default: Any
        """
        if "default" in self.kwargs and self.kwargs["default"] != default:  # pragma: no cover
            logger.warning("default value is overwritten")
        self.kwargs["default"] = default

    def set_nargs(self, /, nargs: Union[int, str, None]) -> None:
        """
        Sets the number of arguments for the argument.

        :param nargs: The number of arguments for the argument.
        :type nargs: Union[int, str, None]
        """
        if "nargs" in self.kwargs and self.kwargs["nargs"] != nargs:  # pragma: no cover
            logger.warning("nargs is overwritten")
        self.kwargs["nargs"] = nargs

    def __class_getitem__(cls, args: Any) -> Annotated:
        """
        Provides a way to specify argument types and options using the Argument class.

        :param args: The type and options for the argument.
        :type args: Any
        :return: An Annotated type with the specified argument.
        :rtype: Annotated
        """
        if not isinstance(args, tuple):
            tp = args
            args = ()
        else:
            tp, *args = args

        if args and isinstance(args[-1], cls):
            arg_ins: Self
            *args, arg_ins = args
            arg_ins.args = tuple(args) + arg_ins.args
            return Annotated[tp, arg_ins]
        elif args and isinstance(args[-1], Mapping):
            *args, kwargs = args
            if "type" not in kwargs and "action" not in kwargs:
                kwargs["type"] = tp
        elif tp is bool:
            kwargs = {"action": "store_true"}
        else:
            kwargs = {"type": tp}

        if not all(isinstance(arg, str) for arg in args):
            raise TypeError("argument name must be str")
        return Annotated[tp, cls(*args, **kwargs)]  # type: ignore

    def __call__(self, parser: _ArgumentParser) -> _ArgumentParser:
        """
        Adds the argument to the provided ArgumentParser.

        :param parser: The ArgumentParser to add the argument to.
        :type parser: ArgumentParser
        :return: The ArgumentParser with the argument added.
        :rtype: ArgumentParser
        """
        parser.add_argument(*self.args, **self.kwargs)
        return parser

    @_CoreSchemaGetter
    def __get_pydantic_core_schema__(self, source: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        if self.__class__ is source or get_origin(source) is self.__class__:
            return core_schema.is_instance_schema(self.__class__)

        def _validate_arguments(v: Any, info: core_schema.ValidationInfo) -> Any:
            if v is not EMPTY:
                return v

            if (
                info.context is None
                or "signature" not in info.context
                or "invoker" not in info.context
                or "extra_data" not in info.context
            ):
                raise ValueError("context is not set")
            extra_data = info.context["extra_data"]
            ns = extra_data.get("argparse_namespace")
            if ns is None:
                sig = info.context["signature"]
                invoker: HandlerInvoker = info.context["invoker"]
                identifier = info.context.get("identifier") or "__invoker__"

                session = invoker.get_dependency(Parameter("session", Parameter.POSITIONAL_OR_KEYWORD), **info.context)
                argv = invoker.get_dependency(Parameter("argv", Parameter.POSITIONAL_OR_KEYWORD), **info.context)

                parser = build_parser(
                    sig,
                    unannotated_mode="ignore",
                    parser_factory=partial(ArgumentParser, session, prog=identifier),
                )

                ns = parser.parse_args(argv)
                extra_data["argparse_parser"] = parser
                extra_data["argparse_namespace"] = ns
            dest = self.kwargs.get("dest")
            if dest is None and self.args:
                dest = self.args[-1].lstrip("-")
            if not dest:
                raise ValueError("dest is not set")
            return getattr(ns, dest)

        return core_schema.with_info_before_validator_function(_validate_arguments, handler(source))

    def __eq__(self, value: Any) -> bool:
        if not isinstance(value, Argument):
            return False
        return self.args == value.args and self.kwargs == value.kwargs

    __hash__ = object.__hash__

    def __repr__(self) -> str:
        """
        Returns a string representation of the Argument instance.

        :return: A string representation of the Argument instance.
        :rtype: str
        """
        return f"{self.__class__.__qualname__}({self.args}, {self.kwargs})"


if TYPE_CHECKING:
    Arg = Annotated
else:
    Arg = Argument


def get_argument(annotation: Any) -> Optional[Argument]:
    """
    Retrieves the Argument instance from an annotation.

    :param annotation: The annotation to retrieve the Argument instance from.
    :type annotation: Any
    :return: The Argument instance if found, otherwise None.
    :rtype: Optional[Argument]
    """
    if isinstance(annotation, Argument):
        return annotation
    if get_origin(annotation) is not Annotated:
        return

    _, *metadata = get_args(annotation)
    for arg in metadata:
        if isinstance(arg, Argument):
            return arg


_T_Parser = TypeVar("_T_Parser", bound=_ArgumentParser)


def build_parser(
    func: Union[Callable, Signature],
    *,
    unannotated_mode: Literal["strict", "autoconvert", "ignore"] = "strict",
    parser_factory: Callable[..., _T_Parser] = _ArgumentParser,
) -> _T_Parser:
    """
    Builds an `ArgumentParser` from the annotated signature of a function.

    :param func: The function whose signature defines the CLI arguments.
    :param unannotated_mode: How to handle parameters without `Argument` metadata.
        Valid options: "strict" (error), "autoconvert" (infer from type), "ignore".
    :return: Configured `ArgumentParser`.

    Usage:
        def example(
            path: Arg[str, "--path", Argument(help="Input path")],
            force: Arg[bool, "--force", Argument(action="store_true")],
            timeout: int = 10,
        ) -> None: ...

        parser = build_parser(example, unannotated_mode="autoconvert")
    """
    if isinstance(func, Signature):  # pragma: no cover
        sig = func
        parser = parser_factory()
        type_hints = {}
    else:
        parser = parser_factory(prog=func.__name__, description=func.__doc__)
        sig = signature(func)
        type_hints = get_type_hints(func, include_extras=True)

    for param_name, param in sig.parameters.items():
        annotation = type_hints.get(param_name, param.annotation)
        if param.kind == Parameter.VAR_KEYWORD:
            raise TypeError("var keyword arguments are not supported")
        argument = get_argument(annotation)
        if argument is None:
            if unannotated_mode == "strict":
                raise TypeError(f"{param_name} is not annotated with Argument")
            elif unannotated_mode == "autoconvert":
                argument = get_argument(Arg[annotation]) if annotation is not Parameter.empty else Argument()
                if argument is None:
                    raise TypeError(f"{param_name} is not annotated with Argument and cannot be inferred from type")
            elif unannotated_mode == "ignore":
                continue
            else:
                raise ValueError(f"unsupported unannotated_mode: {unannotated_mode}")

        argument.set_name(param_name, keyword=param.kind == Parameter.KEYWORD_ONLY)
        if param.kind == Parameter.VAR_POSITIONAL:
            argument.set_nargs("*")
        elif param.default is not Parameter.empty:
            argument.set_default(param.default)

        argument(parser)

    return parser
