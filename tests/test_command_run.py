import asyncio

from tinode_grpc import pb

from karuha.command import MessageSession, get_collection, on_command, set_collection
from karuha.event import on
from karuha.event.command import (
    CommandCompleteEvent,
    CommandNotFoundEvent,
    CommandPrepareEvent,
)
from karuha.event.message import get_message_lock
from karuha.exception import KaruhaCommandCanceledError
from karuha.text import Button, Drafty, PlainText

from .utils import TEST_TIME_OUT, AsyncBotTestCase, new_test_message


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


@on(CommandPrepareEvent)
async def command_prepare(event: CommandPrepareEvent) -> None:
    if event.command is should_cancel:
        raise KaruhaCommandCanceledError(name=event.command.name, command=event.command)


class TestCommandRun(AsyncBotTestCase):
    command_collection = get_collection()

    async def test_unexist(self) -> None:
        set_collection(self.command_collection)
        with self.catchEvent(CommandNotFoundEvent) as catcher:
            self.bot.receive_message(
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
        self.bot.receive_content(b'{"txt": "/hello world"}')
        with self.catchEvent(CommandCompleteEvent) as catcher:
            msg = await self.bot.consum_message()
            if msg.note:
                # note read message, ignore it
                msg = await self.bot.consum_message()
            pub_msg = msg.pub
            self.bot.confirm_message(pub_msg.id, seq=0)
            await catcher.catch_event()
        self.assertEqual(pub_msg.topic, "test")
        self.assertEqual(pub_msg.content, b'"Hello world!"')

    async def test_cancel_command(self) -> None:
        set_collection(self.command_collection)
        self.bot.receive_content(b'{"txt": "/should_cancel"}')
        with self.catchEvent(CommandPrepareEvent) as catcher:
            await catcher.catch_event()

    async def test_has_return(self) -> None:
        set_collection(self.command_collection)
        self.bot.receive_content(b'{"txt": "/has_return"}')
        with self.catchEvent(CommandCompleteEvent) as catcher:
            e = await catcher.catch_event()
        self.assertEqual(e.result, 1)

    async def test_session(self) -> None:
        ss = MessageSession(self.bot, new_test_message())
        self.assertEqual(ss.topic, "test")
        self.assertEqual(ss.last_message.user_id, "user")
        self.assertEqual(ss.last_message.plain_text, "test")
        self.assertEqual(len(ss.messages), 1)

        send_task = asyncio.create_task(ss.send(PlainText("test")))
        msg = await self.bot.consum_message()
        self.assertTrue(msg.pub)
        pubmsg = msg.pub
        self.bot.confirm_message(pubmsg.id, seq=0)
        await asyncio.wait_for(send_task, timeout=TEST_TIME_OUT)

        wait_task = asyncio.create_task(ss.wait_reply())
        self.bot.receive_content(b'{"txt": "test1"}', topic="test1")
        self.bot.receive_content(b'{"txt": "test"}', from_user_id="user1")
        msg = await asyncio.wait_for(wait_task, timeout=TEST_TIME_OUT)
        self.assertEqual(msg.content, b'{"txt": "test"}')

    async def test_session_form(self) -> None:
        ss = MessageSession(self.bot, new_test_message())
        form_task = asyncio.create_task(
            ss.send_form(
                "title", "Yes", Button(text="No"), Button(text="Cancel", name="cancel")
            )
        )
        msg = await self.bot.consum_message()
        self.assertTrue(get_message_lock().locked())
        self.assertTrue(msg.pub)
        pubmsg = msg.pub
        self.bot.confirm_message(pubmsg.id, seq=114)
        self.bot.receive_content(
            b'{"ent":[{"data":{"mime":"application/json","val":{"resp":{"yes":1},"seq":114}},'
            b'"tp":"EX"}],"fmt":[{"at":-1}],"txt":"Yes"}',
        )
        bid = await asyncio.wait_for(form_task, timeout=TEST_TIME_OUT)
        self.assertEqual(bid, 0)

    async def test_session_form1(self) -> None:
        ss = MessageSession(self.bot, new_test_message())
        form_task = asyncio.create_task(
            ss.send_form(
                "title", "Yes", Button(text="No"), Button(text="Cancel", name="cancel")
            )
        )
        msg = await self.bot.consum_message()
        self.assertTrue(get_message_lock().locked())
        self.assertTrue(msg.pub)
        pubmsg = msg.pub
        self.bot.confirm_message(pubmsg.id, seq=114)
        self.bot.receive_content(
            b'{"ent":[{"data":{"mime":"application/json","val":{"seq":114}},"tp":"EX"}],'
            b'"fmt":[{"at":-1}],"txt":"No"}',
        )
        bid = await asyncio.wait_for(form_task, timeout=TEST_TIME_OUT)
        self.assertEqual(bid, 1)

    async def test_session_form2(self) -> None:
        ss = MessageSession(self.bot, new_test_message())
        form_task = asyncio.create_task(
            ss.send_form(
                "title",
                "Yes",
                Button(text="No"),
                Button(text="Cancel", name="cancel", val="cancel"),
            )
        )
        msg = await self.bot.consum_message()
        self.assertTrue(get_message_lock().locked())
        self.assertTrue(msg.pub)
        pubmsg = msg.pub
        self.bot.confirm_message(pubmsg.id, seq=114)
        self.bot.receive_content(
            b'{"ent":[{"data":{"mime":"application/json","val":{"resp":{"cancel":"cancel"},'
            b'"seq":114}},"tp":"EX"}],"fmt":[{"at":-1}],"txt":"Cancel"}',
        )
        bid = await asyncio.wait_for(form_task, timeout=TEST_TIME_OUT)
        self.assertEqual(bid, 2)
