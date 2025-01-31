import asyncio

from karuha.exception import KaruhaRuntimeError
from karuha.session import BaseSession, MessageSession
from karuha.event.message import get_message_lock
from karuha.text import Drafty, Button, File, Image, drafty2text

from .utils import TEST_UID, AsyncBotTestCase, new_test_message, TEST_TIMEOUT, TEST_TOPIC


class TestSession(AsyncBotTestCase):
    async def test_init(self) -> None:
        async def session_task() -> BaseSession:
            async with BaseSession(self.bot, TEST_TOPIC) as ss:
                self.assertFalse(ss.closed)
            return ss
        task = asyncio.create_task(session_task())
        await self.assert_bot_sub(TEST_TOPIC)
        ss = await self.wait_for(task)
        self.assertTrue(ss.closed)
        with self.assertRaises(KaruhaRuntimeError):
            await ss.send("test")
        with self.assertRaises(KaruhaRuntimeError):
            async with ss:
                pass

    async def test_send(self) -> None:
        ss = MessageSession(self.bot, new_test_message())
        self.assertEqual(ss.topic, TEST_TOPIC)
        self.assertEqual(ss.last_message.user_id, TEST_UID)
        self.assertEqual(ss.last_message.plain_text, "test")
        self.assertEqual(len(ss.messages), 1)

        send_task = asyncio.create_task(ss.send("test\n", replace=114))

        pubmsg = await self.get_bot_pub()
        self.assertEqual(pubmsg.topic, TEST_TOPIC)
        self.assertNotIn(b"\n", pubmsg.content)
        self.assertEqual(
            pubmsg.head,
            {"replace": b'":114"', "auto": b"true", "mime": b'"text/x-drafty"'},
        )
        await self.wait_for(send_task)

        wait_task = asyncio.create_task(ss.wait_reply())
        await self.put_bot_content(b'{"txt": "test1"}', topic="grp_test1")
        await self.put_bot_content(b'{"txt": "test"}', from_user_id="user1")
        msg = await self.wait_for(wait_task)
        self.assertEqual(msg.content, b'{"txt": "test"}')

    async def test_form(self) -> None:
        ss = MessageSession(self.bot, new_test_message())
        form_task = asyncio.create_task(
            ss.send_form(
                "title", "Yes", Button(text="No"), Button(text="Cancel", name="cancel")
            )
        )
        await self.get_bot_pub(seq=114)
        self.assertTrue(get_message_lock().locked())
        await self.put_bot_content(
            b'{"ent":[{"data":{"mime":"application/json","val":{"resp":{"yes":1},"seq":114}},'
            b'"tp":"EX"}],"fmt":[{"at":-1}],"txt":"Yes"}',
        )
        bid = await asyncio.wait_for(form_task, timeout=TEST_TIMEOUT)
        async with get_message_lock():
            pass
        self.assertEqual(bid, 0)

    async def test_form1(self) -> None:
        ss = MessageSession(self.bot, new_test_message())
        form_task = asyncio.create_task(
            ss.send_form(
                "title", "Yes", Button(text="No"), Button(text="Cancel", name="cancel")
            )
        )
        await self.get_bot_pub(seq=114)
        self.assertTrue(get_message_lock().locked())
        await self.put_bot_content(
            b'{"ent":[{"data":{"mime":"application/json","val":{"seq":114}},"tp":"EX"}],'
            b'"fmt":[{"at":-1}],"txt":"No"}',
        )
        bid = await asyncio.wait_for(form_task, timeout=TEST_TIMEOUT)
        self.assertEqual(bid, 1)

    async def test_form2(self) -> None:
        ss = MessageSession(self.bot, new_test_message())
        form_task = asyncio.create_task(
            ss.send_form(
                "title",
                "Yes",
                Button(text="No"),
                Button(text="Cancel", name="cancel", val="cancel"),
            )
        )
        await self.get_bot_pub(seq=114)
        self.assertTrue(get_message_lock().locked())
        await self.put_bot_content(
            b'{"ent":[{"data":{"mime":"application/json","val":{"resp":{"cancel":"cancel"},'
            b'"seq":114}},"tp":"EX"}],"fmt":[{"at":-1}],"txt":"Cancel"}',
        )
        bid = await asyncio.wait_for(form_task, timeout=TEST_TIMEOUT)
        self.assertEqual(bid, 2)

    async def test_file(self) -> None:
        ss = MessageSession(self.bot, new_test_message())
        file_task = asyncio.create_task(ss.send_file("karuha/version.py"))
        pubmsg = await self.get_bot_pub()
        df = Drafty.model_validate_json(pubmsg.content)
        self.assertEqual(df.txt, '')
        ft = drafty2text(df)
        assert isinstance(ft, File)
        self.assertEqual(ft.name, 'version.py')
        self.assertIsNotNone(ft.val)
        await self.wait_for(file_task)

    async def test_image(self) -> None:
        ss = MessageSession(self.bot, new_test_message())
        image_task = asyncio.create_task(ss.send_image("docs/img/tw_icon-karuha2.png"))
        pubmsg = await self.get_bot_pub()
        df = Drafty.model_validate_json(pubmsg.content)
        self.assertEqual(df.txt, '')
        ft = drafty2text(df)
        assert isinstance(ft, Image)
        self.assertEqual(ft.name, 'tw_icon-karuha2.png')
        self.assertIsNotNone(ft.ref or ft.val)
        await self.wait_for(image_task)

    async def test_get_data(self) -> None:
        ss = BaseSession(self.bot, TEST_TOPIC)

        # test get single data
        task = asyncio.create_task(ss.get_data(seq_id=114))
        await self.assert_bot_sub()
        getmsg = await self.get_bot_sent()
        self.assertTrue(getmsg.HasField("get"))
        self.assertEqual(getmsg.get.query.data.since_id, 114)
        self.assertEqual(getmsg.get.query.data.before_id, 115)
        await self.put_bot_content(b"\"test\"", topic=TEST_TOPIC, seq_id=114)
        msg = await self.wait_for(task)
        self.assertEqual(msg.content, b"\"test\"")

        # test get data from cache
        msg = await self.wait_for(ss.get_data(seq_id=114))
        self.assertEqual(msg.content, b"\"test\"")

        # test get data range
        task = asyncio.create_task(ss.get_data(low=113, hi=115))
        getmsg = await self.get_bot_sent()
        if getmsg.HasField("note"):
            getmsg = await self.get_bot_sent()
        self.assertTrue(getmsg.HasField("get"), getmsg)
        self.assertEqual(getmsg.get.query.data.since_id, 113)
        self.assertEqual(getmsg.get.query.data.before_id, 114)
        await self.put_bot_content(b"\"113\"", topic=TEST_TOPIC, seq_id=113)
        getmsg = await self.get_bot_sent()
        if getmsg.HasField("note"):
            getmsg = await self.get_bot_sent()
        self.assertTrue(getmsg.HasField("get"), getmsg)
        self.assertEqual(getmsg.get.query.data.since_id, 115)
        self.assertEqual(getmsg.get.query.data.before_id, 116)
        await self.put_bot_content(b"\"115\"", topic=TEST_TOPIC, seq_id=115)
        msgs = await self.wait_for(task)
        self.assertEqual(msgs[0].content, b"\"113\"")
        self.assertEqual(msgs[1].content, b"\"test\"")
        self.assertEqual(msgs[2].content, b"\"115\"")
    
    async def test_topic(self) -> None:
        ss = BaseSession(self.bot, "test_topic")
        task = asyncio.create_task(ss.subscribe(force=True))
        await self.assert_bot_sub()
        await self.wait_for(task)

        task = asyncio.create_task(ss.leave())
        await self.assert_bot_leave()
        await self.wait_for(task)
