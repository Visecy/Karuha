from karuha import on_command, MessageSession


@on_command
async def echo(session: MessageSession, text: str):
    argv = text.split(None, 1)
    if len(argv) >= 1:
        await session.send(argv[1])
