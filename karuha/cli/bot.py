from typing_extensions import Annotated

from ptcmd import Argument, auto_argument
from rich.table import Table
from rich.columns import Columns

from ..runner import get_all_bots
from .app import App


class BotApp(App):
    __slots__ = []
    
    @auto_argument
    def do_bot(self) -> None:
        pass

    @do_bot.add_subcommand("list")
    def bot_list(self, *, verbose: Annotated[bool, Argument("-v", "--verbose", action="store_true")] = False) -> None:
        bots = get_all_bots()
        if verbose:
            table = Table(title="bots", show_header=True, header_style="bold magenta")
            table.add_column("name")
            table.add_column("user_id")
            table.add_column("status")
            for bot in bots:
                table.add_row(bot.name, str(bot.user_id), bot.state.name)
        else:
            table = Columns()
            for bot in bots:
                table.add_renderable(bot.name)
        self.poutput(table)
    
    # @do_bot.add_subcommand("add")

