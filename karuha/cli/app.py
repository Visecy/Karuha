from typing import Any, Optional, TextIO
from rich.theme import Theme
from ptcmd import Cmd
from ptcmd.theme import DEFAULT_STYLE


STYLE = {
    "prompt.host": "bold green",
    "prompt.user": "bold blue",
    **DEFAULT_STYLE
}


class App(Cmd):
    __slots__ = ["bot"]

    DEFAULT_PROMPT = "[green]karuha-cli[/green]$ "
    

