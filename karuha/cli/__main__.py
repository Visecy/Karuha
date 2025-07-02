import asyncio
import platform
import sys
from argparse import ArgumentParser
from functools import partial
from pathlib import Path
from typing import Optional

from ptcmd.argument import Argument, invoke_from_argv
from rich.logging import RichHandler
from typing_extensions import Annotated

from .. import CONFIG_PATH
from ..config import load_config
from ..logger import console_handler
from ..runner import get_bot
from ..version import APP_VERSION, LIB_VERSION
from .cli import Cli


description = """
A easy way to run chatbots from a configuration file
""".strip()

version_info = " ".join(
    (f"%(prog)s v{APP_VERSION}", f"({platform.system()}/{platform.release()});", f"gRPC-python/{LIB_VERSION}")
)

default_config = CONFIG_PATH


def run_cli(
    config: Path = CONFIG_PATH,
    *,
    auto_create: Annotated[bool, Argument(action="store_true", help="auto create config")] = False,
    version: Annotated[str, Argument("-V", "--version", action="version", version=version_info)] = version_info,
    bot: Annotated[Optional[str], Argument("-b", "--bot", help="bot name")] = None,
) -> None:
    load_config(config, auto_create=auto_create)
    bot_ins = get_bot(bot) if bot is not None else None
    app = Cli(bot=bot_ins)

    assert isinstance(console_handler, RichHandler)
    console_handler.console = app.console
    try:
        sys.exit(app.cmdloop())
    except asyncio.CancelledError:
        sys.exit(1)


def main() -> None:
    invoke_from_argv(
        run_cli,
        sys.argv[1:],
        unannotated_mode="autoconvert",
        parser_factory=partial(ArgumentParser, prog="karuha-cli", description=description),
    )


if __name__ == "__main__":
    main()
