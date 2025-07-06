import asyncio
from typing import Any, Optional, TextIO

from ptcmd import Cmd
from ptcmd.theme import DEFAULT_STYLE
from rich.theme import Theme

from ..bot import Bot
from ..runner import async_run
from ..session import MessageSession


STYLE = {
    "prompt.host": "bold green",
    "prompt.bot": "bold blue",
    **DEFAULT_STYLE
}


class App(Cmd):
    __slots__ = ["_bot", "message_session", "_runner_task", "_current_task"]

    DEFAULT_PROMPT = "[prompt.host]karuha-cli[/prompt.host]$ "
    DEFAULT_PROMPT_WITH_BOT = "[prompt.host]{user_id}@karuha-cli[/prompt.host]$ "
    DEFAULT_THEME = Theme(STYLE)

    def __init__(
        self,
        stdin: Optional[TextIO] = None,
        stdout: Optional[TextIO] = None,
        *,
        bot: Optional[Bot] = None,
        **kwds: Any
    ) -> None:
        super().__init__(stdin, stdout, **kwds)
        self._bot = bot
        self.message_session: Optional[MessageSession] = None
        self._runner_task = None
        self._update_prompt()

    def preloop(self) -> None:
        self._current_task = asyncio.current_task()
        self._runner_task = asyncio.create_task(async_run())
        self._runner_task.add_done_callback(self._task_callback)
    
    def postloop(self) -> None:
        if self._runner_task is None:
            return
        task = self._runner_task
        self._runner_task = self._current_task = None
        task.cancel()
    
    async def emptyline(self) -> Optional[bool]:
        return

    @property
    def bot(self) -> Optional[Bot]:
        return self._bot
    
    @bot.setter
    def bot(self, bot: Optional[Bot]) -> None:
        self._bot = bot
        self._update_prompt()

    def _update_prompt(self) -> None:
        if self._bot is None:
            self.prompt = self.DEFAULT_PROMPT
            return
        self.prompt = self.DEFAULT_PROMPT_WITH_BOT.format(user_id=self._bot.user_id)
    
    def _task_callback(self, task: asyncio.Task) -> None:
        if self._runner_task is None:
            return
        if self._current_task is not None:
            self._current_task.cancel()
    