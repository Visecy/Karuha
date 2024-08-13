from typing import List, Optional

from pydantic_core import ValidationError

from karuha import MessageSession, on_command
from karuha.text import Drafty, Head, Message
from karuha.utils.argparse import ArgumentParser


@on_command
async def echo(session: MessageSession, message: Message, argv: List[str], reply: Head[Optional[int]]) -> None:
    parser = ArgumentParser(session, "echo")
    parser.add_argument("-r", "--raw", action="store_true", help="echo raw text")
    parser.add_argument("-d", "--drafty", action="store_true", help="decode text as drafty")
    parser.add_argument("-R", "--reply", action="store_true", help="echo reply message")
    parser.add_argument("text", nargs="*", help="text to echo", default=())
    ns = parser.parse_args(argv)
    if ns.reply:
        if reply is None:
            await session.finish("No reply message")
        message = await session.get_data(seq_id=reply)
        text = message.plain_text
    else:
        text = " ".join(ns.text)
    if ns.raw:
        raw_text = message.raw_text
        if isinstance(raw_text, Drafty):
            raw_text = raw_text.model_dump_json(indent=4, exclude_defaults=True)
        await session.finish(raw_text)
    elif ns.drafty:
        try:
            df = Drafty.model_validate_json(text)
        except ValidationError:
            await session.finish("Invalid Drafty JSON")
        await session.send(df)
    else:
        await session.send(text)
