import asyncio

from karuha.command import MessageSession
from karuha.event.message import get_message_lock
from karuha.text import Drafty, PlainText, Button, File, Image, drafty2text

from .utils import AsyncBotTestCase, new_test_message, TEST_TIME_OUT


class TestSession(AsyncBotTestCase):
    async def test_send(self) -> None:
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

    async def test_form(self) -> None:
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

    async def test_form1(self) -> None:
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
    
    async def test_file(self) -> None:
        ss = MessageSession(self.bot, new_test_message())
        file_task = asyncio.create_task(ss.send_file("README.md"))
        msg = await self.bot.consum_message()
        self.assertTrue(msg.pub)
        pubmsg = msg.pub
        df = Drafty.model_validate_json(pubmsg.content)
        self.assertEqual(df.txt, '')
        ft = drafty2text(df)
        assert isinstance(ft, File)
        self.assertEqual(ft.name, 'README.md')
        self.assertIsNotNone(ft.val)
        self.bot.confirm_message(pubmsg.id, seq=0)
        await asyncio.wait_for(file_task, timeout=TEST_TIME_OUT)
    
    async def test_image(self) -> None:
        ss = MessageSession(self.bot, new_test_message())
        image_task = asyncio.create_task(ss.send_image("docs/img/tw_icon-karuha2.png"))
        msg = await self.bot.consum_message()
        self.assertTrue(msg.pub)
        pubmsg = msg.pub
        df = Drafty.model_validate_json(pubmsg.content)
        self.assertEqual(df.txt, '')
        ft = drafty2text(df)
        assert isinstance(ft, Image)
        self.assertEqual(ft.name, 'tw_icon-karuha2.png')
        self.assertIsNotNone(ft.val)
        self.bot.confirm_message(pubmsg.id, seq=0)
        await asyncio.wait_for(image_task, timeout=TEST_TIME_OUT)
