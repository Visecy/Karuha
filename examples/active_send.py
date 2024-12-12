import asyncio
import sys

from prompt_toolkit import prompt
from prompt_toolkit.patch_stdout import patch_stdout

import karuha
from karuha.event.bot import BotReadyEvent
from karuha.logger import console_handler
from karuha.session import BaseSession


TOPIC = "grp_test"


def read(queue: asyncio.Queue) -> None:
    loop = karuha.runner._get_running_loop()
    with patch_stdout():
        old_stream = console_handler.stream
        console_handler.setStream(sys.stdout)
        while True:
            try:
                text = prompt("> ")
            except KeyboardInterrupt:
                break
            loop.call_soon_threadsafe(queue.put_nowait, text)
        console_handler.setStream(old_stream)


@karuha.on(BotReadyEvent)
async def handle(bot: karuha.Bot) -> None:
    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(None, read, queue)
    future.add_done_callback(lambda _: bot.cancel())

    async with BaseSession(bot, TOPIC) as ss:
        while True:
            text = await queue.get()
            await ss.send(text)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <topic>")
        sys.exit(1)
    TOPIC = sys.argv[1]
    karuha.load_config()
    karuha.run()
