import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

import karuha
from karuha.event.bot import BotReadyEvent
from karuha.session import BaseSession


TOPIC = "grp_test"


@karuha.on(BotReadyEvent)
async def handle(bot: karuha.Bot) -> None:
    async with BaseSession(bot, TOPIC) as ss:
        prompt_ss = PromptSession()
        with patch_stdout():
            while True:
                text = await prompt_ss.prompt_async(message="> ")
                if text:
                    await ss.send(text)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <topic>")
        sys.exit(1)
    TOPIC = sys.argv[1]
    karuha.load_config()
    karuha.run()
