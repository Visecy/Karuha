from typing import List

from karuha import MessageSession
from karuha.command import on_command, rule
from karuha.utils.argparse import ArgumentParser


@on_command(alias=("hello",), rule=rule(to_me=True))
async def hi(session: MessageSession, name: str, user_id: str, argv: List[str]) -> None:
    parser = ArgumentParser(session, name)
    parser.add_argument("name", nargs="*", help="name to greet")
    parser.add_argument("-p", "--in-private", action="store_true", help="send message in private chat")
    ns = parser.parse_args(argv)
    if ns.name:
        name = ' '.join(ns.name)
    else:
        user = await session.get_user(user_id)
        name = user.fn or "world"
    await session.send(f"Hello {name}!", topic=user_id if ns.in_private else None)
