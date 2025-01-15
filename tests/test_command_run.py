from pydantic_core import from_json, to_json
from tinode_grpc import pb

from karuha.command import MessageSession, get_collection, on_rule, on_command, set_collection
from karuha.event import on
from karuha.event.command import (
    CommandCompleteEvent,
    CommandNotFoundEvent,
    CommandPrepareEvent,
)
from karuha.exception import KaruhaCommandCanceledError
from karuha.text import Drafty, Mention

from .utils import TEST_TOPIC, AsyncBotTestCase


@on_command(alias=("hello",))
async def hi(session: MessageSession, text: str) -> None:
    _, name = text.split(" ", 1)
    await session.send(f"Hello {name}!")


@on_command
async def should_cancel(session: MessageSession, text: str, raw_text: Drafty) -> None:
    pass


@on_command
def has_return() -> int:
    return 1


@on_rule(mention="usr_1")
async def on_mention(session: MessageSession, user_id: str) -> None:
    await session.send(f"{user_id} mentioned you")


@on(CommandPrepareEvent)
def command_prepare(event: CommandPrepareEvent) -> None:
    if event.command is should_cancel:
        raise KaruhaCommandCanceledError


class TestCommandRun(AsyncBotTestCase):
    command_collection = get_collection()

    async def test_unexist(self) -> None:
        set_collection(self.command_collection)
        with self.catchEvent(CommandNotFoundEvent) as catcher:
            await self.put_bot_received(
                pb.ServerMsg(
                    data=pb.ServerData(
                        topic="test",
                        from_user_id="user",
                        head={"auto": b"true"},
                        content=b'"/unexist command"',
                    )
                )
            )
            await catcher.catch_event()

    async def test_hi_command(self) -> None:
        set_collection(self.command_collection)
        await self.put_bot_content(b'{"txt": "/hello world"}')
        with self.catchEvent(CommandCompleteEvent) as catcher:
            pub_msg = await self.get_bot_pub()
            await catcher.catch_event()
        self.assertEqual(pub_msg.topic, TEST_TOPIC)
        self.assertEqual(pub_msg.content, b'"Hello world!"')

    async def test_cancel_command(self) -> None:
        set_collection(self.command_collection)
        await self.put_bot_content(b'{"txt": "/should_cancel"}')
        with self.catchEvent(CommandPrepareEvent) as catcher:
            await catcher.catch_event()

    async def test_has_return(self) -> None:
        set_collection(self.command_collection)
        await self.put_bot_content(b'{"txt": "/has_return"}')
        with self.catchEvent(CommandCompleteEvent) as catcher:
            e = await catcher.catch_event()
        self.assertEqual(e.result, 1)
    
    async def test_on_rule(self) -> None:
        set_collection(self.command_collection)
        await self.put_bot_content(to_json(Mention(text="@1", val="usr_1").to_drafty()), from_user_id="usr_2")
        pub_msg = await self.get_bot_pub()
        self.assertEqual(from_json(pub_msg.content), "usr_2 mentioned you")
