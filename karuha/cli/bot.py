from argparse import _StoreAction
from typing import List, Literal, Optional
from uuid import uuid4
from typing_extensions import Annotated

from ptcmd import Argument, auto_argument
from rich.table import Table
from rich.columns import Columns

from ..config import Bot as BotConfig
from ..runner import get_all_bots, remove_bot, try_get_bot
from ..service import BotService
from .app import App


class BotNameAction(_StoreAction):
    @property
    def choices(self) -> List[str]:
        return [bot.name for bot in get_all_bots()]

    @choices.setter
    def choices(self, _: List[str]) -> None:
        pass


class BotApp(App):
    __slots__ = ["_bot_service"]
    
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
                table.add_row(bot.name, getattr(bot, "user_id", "(none)"), bot.state.name)
        else:
            table = Columns()
            for bot in bots:
                table.add_renderable(bot.name)
        self.poutput(table)
    
    @do_bot.add_subcommand("use")
    def bot_use(self, name: Annotated[str, Argument(action=BotNameAction)]) -> None:
        bot = try_get_bot(name)
        if bot is None:
            self.perror(f"bot {name} not found")
        else:
            self.poutput(f"use bot {name} ({bot.user_id})")
            self.bot = bot

    @do_bot.add_subcommand("add")
    async def bot_add(
        self,
        name: Optional[str] = None,
        *,
        scheme: Literal["basic", "token", "cookie"] = "basic",
        secret: str,
        no_auto_login: bool = False,
        use: bool = False,
    ) -> None:
        if name is None:
            name = f"chatbot_{uuid4()}"
        config = BotConfig(name=name, scheme=scheme, secret=secret, auto_login=not no_auto_login)
        bot = await self.bot_service.attach(config, run=True)
        if use:
            self.bot_use(bot.name)
    
    @do_bot.add_subcommand("remove")
    def remove_bot(self, name: Annotated[str, Argument(action=BotNameAction)]) -> None:
        if self.bot is not None and self.bot.name == name:
            self.perror("Cannot remove the current bot")
        else:
            remove_bot(name)
    
    @property
    def bot_service(self) -> BotService:
        if self.bot is None:
            raise ValueError("No bot is used")
        if hasattr(self, "_bot_service") and self._bot_service.bot is self.bot:
            return self._bot_service
        self._bot_service = BotService(self.bot)
        return self._bot_service
