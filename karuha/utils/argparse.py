import asyncio
from argparse import ArgumentParser as _ArgumentParser
from functools import partial
from inspect import Parameter
from types import MethodType
from typing import TYPE_CHECKING, Any, Callable, NoReturn, Optional, Type
from weakref import WeakSet

from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema
from ptcmd.argument import Argument as _Argument
from ptcmd.argument import build_parser
from typing_extensions import Annotated, get_origin

from .invoker import EMPTY, HandlerInvoker

from ..exception import KaruhaCommandCanceledError
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


class Argument(_Argument):
    """
    Represents a command-line argument to be added to an ArgumentParser.

    This class allows defining argparse arguments in a declarative way, either directly
    or through type annotations using `Annotated` (aliased as `Arg` for convenience).

    :param args: Positional arguments for the argument.
    :param kwargs: Keyword arguments for the argument.

    Usage:

    ```py
    version: Arg[
        str,
        "-v", "--version",
        {"action": "version", "version": "0.1.0"}
    ]

    # Or using Annotated
    version: Annotated[
        str,
        Argument(
            "-v", "--version",
            action="version",
            version="0.1.0"
        )
    ]
    ```
    """

    __slots__ = []

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


if TYPE_CHECKING:
    Arg = Annotated
else:
    Arg = Argument
