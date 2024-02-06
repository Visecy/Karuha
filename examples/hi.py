from karuha import on_command, MessageSession


@on_command(alias=("hello",))
async def hi(session: MessageSession, text: str) -> None:
    total = text.split(' ', 1)
    if len(total) == 1:
        await session.send("Hello!")
    name = total[1]
    await session.send(f"Hello {name}!")
