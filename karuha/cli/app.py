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
    __slots__ = ["bot", "message_session", "_runner_task", "_current_task"]

    DEFAULT_PROMPT = "[prompt.host]karuha-cli[/prompt.host]$ "
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
        self.bot = bot
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

    @property
    def running(self) -> bool:
        return self._runner_task is not None and not self._runner_task.done()

    def _update_prompt(self) -> None:
        if self.bot is None:
            self.prompt = self.DEFAULT_PROMPT
            return
        user_id = self.bot.user_id
        self.prompt = f"[prompt.bot]{user_id}[/prompt.bot]@{self.DEFAULT_PROMPT}"
    
    def _task_callback(self, task: asyncio.Task) -> None:
        if self._runner_task is None:
            return
        if self._current_task is not None:
            self._current_task.cancel()
    