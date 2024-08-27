import asyncio
import sys
from queue import Queue

from prompt_toolkit import prompt
from prompt_toolkit.patch_stdout import patch_stdout

import karuha
from karuha.event.bot import BotReadyEvent
from karuha.logger import console_handler
from karuha.session import BaseSession


TOPIC = "grp_test"


def read(queue: Queue) -> None:
    with patch_stdout():
        old_stream = console_handler.stream
        console_handler.setStream(sys.stdout)
        while True:
            try:
                text = prompt("> ")
            except (IOError, KeyboardInterrupt):
                break
            print(f"< {text}")
            queue.put(text)
        console_handler.setStream(old_stream)


@karuha.on(BotReadyEvent)
async def handle(bot: karuha.Bot) -> None:
    queue = Queue()
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, read, queue)

    async with BaseSession(bot, TOPIC) as ss:
        while True:
            text = await loop.run_in_executor(None, queue.get)
            await ss.send(text)


if __name__ == "__main__":
    karuha.load_config()
    karuha.run()
