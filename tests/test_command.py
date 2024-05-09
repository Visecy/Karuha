from inspect import signature
from typing import List, Optional
from unittest import TestCase

from pydantic_core import to_json

from karuha.bot import Bot
from karuha.text import PlainText, Drafty, Message, Head
from karuha.command.rule import rule
from karuha.command.collection import (add_sub_collection, get_collection, new_collection, remove_sub_collection,
                                       reset_collection, set_collection,
                                       set_collection_factory, set_prefix)
from karuha.command.command import FunctionCommand, ParamFunctionCommand
from karuha.command.parser import SimpleCommandParser
from karuha.exception import KaruhaCommandError, KaruhaHandlerInvokerError
from karuha.text.textchain import Mention, NewLine, Quote, TextChain

from .utils import bot_mock, new_test_message, new_test_command_message


class TestCommand(TestCase):
    def test_name_parser(self) -> None:
        simple_parser = SimpleCommandParser(["!"])
        message0 = new_test_message(b"!test")
        self.assertEqual(simple_parser.parse(message0), ("test", []))
        message1 = new_test_message(b"\"!test\"")
        self.assertEqual(simple_parser.parse(message1), ("test", []))
        message2 = new_test_message(b"{\"txt\": \"test\"}")
        self.assertIsNone(simple_parser.parse(message2))
        message3 = new_test_message(b"\"!!test test test test\"")
        self.assertEqual(
            simple_parser.parse(message3),
            ("!test", [PlainText("test"), PlainText("test"), PlainText("test")])
        )
        message4 = new_test_message(b"\"!\"")
        self.assertEqual(simple_parser.parse(message4), ('', []))
        message5 = new_test_message(b"\"\"")
        self.assertIsNone(simple_parser.parse(message5))

    def test_invoker(self) -> None:

        def cmd_meta(
            bot: Bot,
            message: Message,
            /,
            user_id: Optional[str],
            content: bytes,
            argc: int,
            argv: List[str],
            test: Head,
            undefined: None = None
        ) -> int:
            return 114

        sig = signature(cmd_meta)
        msg = new_test_command_message()
        args, kwargs = msg.extract_handler_params(sig)
        self.assertEqual(args, [bot_mock, msg])
        self.assertEqual(
            kwargs,
            {
                "user_id": "user", "content": b"\"test\"",
                "argc": 0, "argv": [], "test": None, "undefined": None
            }
        )
        self.assertEqual(msg.call_handler(cmd_meta), 114)

        with self.assertRaises(KaruhaHandlerInvokerError):
            msg.call_handler(lambda *message: ...)

        def cmd_text(text: PlainText, raw_text: Drafty) -> None:
            pass

        with self.assertRaises(KaruhaHandlerInvokerError):
            msg.call_handler(cmd_text)
        sig = signature(cmd_text)
        args, kwargs = new_test_command_message(b"{\"txt\": \"test\"}").extract_handler_params(sig)
        self.assertEqual(args, [])
        self.assertEqual(kwargs, {"text": PlainText("test"), "raw_text": Drafty(txt="test")})

        def cmd_plain_text(text: str, raw_text: str) -> None:
            pass

        sig = signature(cmd_plain_text)
        args, kwargs = new_test_command_message(b"{\"txt\": \"test\"}").extract_handler_params(sig)
        self.assertEqual(args, [])
        self.assertEqual(kwargs, {"text": "test", "raw_text": "test"})

        def cmd_no_annotation(text, /, raw_text, content, undefined=None) -> None:
            pass

        sig = signature(cmd_no_annotation)
        args, kwargs = new_test_command_message(b"{\"txt\": \"test\"}").extract_handler_params(sig)
        self.assertEqual(args, [PlainText("test")])
        self.assertEqual(kwargs, {"raw_text": Drafty(txt="test"), "content": b"{\"txt\": \"test\"}", "undefined": None})

    def test_function_command(self) -> None:
        with new_collection() as clt:
            called = False

            with self.assertRaises(KaruhaCommandError):
                clt["test"]

            @clt.on_command("test")
            def test(bot: Bot, /, message: Message, *, text: PlainText) -> None:
                nonlocal called
                called = True

            self.assertIsInstance(test, FunctionCommand)
            self.assertIs(clt["test"], test)
            test(bot_mock, new_test_message(), text=PlainText("test"))
            self.assertTrue(called)

            with self.assertRaises(ValueError):
                clt.add_command(test)

    def test_collection(self) -> None:
        reset_collection()
        set_prefix('/', '#')
        c = new_collection()
        self.assertFalse(c.activated)
        self.assertIsInstance(c.name_parser, SimpleCommandParser)
        self.assertEqual(c.name_parser.prefixs, ('/', '#'))  # type: ignore
        cd = get_collection()
        self.assertTrue(cd.activated)
        self.assertNotEqual(c, cd)
        with self.assertRaises(RuntimeError):
            set_prefix('!')

        reset_collection()
        set_prefix('/')
        set_collection_factory(lambda: c)

        @self.addCleanup
        def cleanup() -> None:
            reset_collection()
            set_collection_factory(None)

        self.assertIs(get_collection(), c)
        with self.assertRaises(RuntimeError):
            set_collection_factory(lambda: c)
        set_collection(cd)
        self.assertIs(get_collection(), cd)
        set_collection_factory(lambda: c, reset=True)
        self.assertIs(get_collection(), c)

    def test_sub_collection(self) -> None:
        reset_collection()
        c = new_collection()
        c.add_command(ParamFunctionCommand.from_function(lambda bot: ..., name="test"))

        cd = get_collection()
        cd.sub_collections.append(c)
        with self.assertRaises(KeyError):
            remove_sub_collection(c)
        self.assertIsNotNone(cd.get_command("test"))

        add_sub_collection(c)
        reset_collection()
        cd1 = get_collection()
        self.assertIsNot(cd, cd1)
        self.assertEqual(cd1.sub_collections, [c])
    
    def test_rule(self) -> None:
        msg = new_test_command_message(to_json("Hello World!"))
        rk = rule(keyword="Hello")
        self.assertEqual(rk.match(msg), 1.0)
        rt = rule(topic="test")
        self.assertEqual(rt.match(msg), 1.0)
        rs = rule(topic="test", seq_id=1)
        self.assertEqual(rs.match(msg), 1.0)
        ru = rule(user_id="user")
        self.assertEqual(ru.match(msg), 1.0)
        rr = rule(regex=r"W.+d")
        self.assertEqual(rr.match(msg), 1.0)
        ra = rk & rt
        self.assertEqual(ra.match(msg), 1.0)
        rn = ~rt
        self.assertEqual(rn.match(msg), 0.0)
        ro = rk | rn
        self.assertEqual(ro.match(msg), 1.0)

        msg = Message.new(
            bot_mock,
            "test",
            "usr",
            1,
            {"reply": "1"},
            to_json(TextChain(
                Quote(content=TextChain(Mention(text="@user", val=bot_mock.uid), NewLine, "Quote content ...")),
                "Hello world!"
            ).to_drafty())
        )
        rq = rule(quote=1)
        self.assertEqual(rq.match(msg), 1.0)
        rm = rule(mention=bot_mock.uid)
        self.assertEqual(rm.match(msg), 1.0)
        r2m = rule(to_me=True)
        self.assertEqual(r2m.match(msg), 1.0)
