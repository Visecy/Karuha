from inspect import Parameter, signature
from typing import Optional
from unittest import TestCase

from karuha.bot import Bot
from karuha.command.collection import (get_collection, new_collection,
                                       reset_collection, set_collection,
                                       set_collection_factory, set_prefix)
from karuha.command.command import FunctionCommand
from karuha.command.parser import (BOT_PARAM, SESSION_PARAM,
                                   MetaParamDispatcher, ParamParser,
                                   ParamParserFlag, SimpleCommandNameParser)
from karuha.command.session import MessageSession
from karuha.exception import KaruhaParserError
from karuha.text import Drafty, Message, PlainText

from .utils import bot_mock


def new_test_message(content: bytes = b"\"test\"") -> Message:
    return Message.new(
        bot_mock, "test", "user", 1, {}, content
    )


class TestCommand(TestCase):
    def test_message(self) -> None:
        message = new_test_message(b"test")
        self.assertEqual(message.text, "test")
        self.assertEqual(message.raw_text, "test")
        self.assertEqual(message.content, b"test")

        message = new_test_message(b"\"test\"")
        self.assertIsInstance(message.text, PlainText)
        self.assertEqual(message.text, PlainText("test"))
        self.assertEqual(message.raw_text, "test")

        message = new_test_message(b"{\"txt\": \"test\"}")
        self.assertIsInstance(message.text, PlainText)
        self.assertEqual(message.text, PlainText("test"))
        self.assertIsInstance(message.raw_text, Drafty)
        self.assertEqual(message.raw_text, Drafty(txt="test"))

    def test_name_parser(self) -> None:
        simple_parser = SimpleCommandNameParser(["!"])
        message0 = new_test_message(b"!test")
        self.assertEqual(simple_parser.parse(message0), "test")
        message1 = new_test_message(b"\"!test\"")
        self.assertEqual(simple_parser.parse(message1), "test")
        message2 = new_test_message(b"{\"txt\": \"test\"}")
        self.assertEqual(simple_parser.parse(message2), None)
    
    def test_meta_param_dispatcher(self) -> None:
        with MetaParamDispatcher("test", str, lambda d, x: d.name, ParamParserFlag.MESSAGE_DATA) as d:
            self.assertAlmostEqual(
                d.match(Parameter("test", Parameter.POSITIONAL_ONLY, annotation=str)),
                1.4
            )
            self.assertAlmostEqual(
                d.match(Parameter("test", Parameter.KEYWORD_ONLY, annotation=str, default="test")),
                1.6
            )
            self.assertAlmostEqual(
                d.match(Parameter("test", Parameter.KEYWORD_ONLY)),
                1.2
            )
            self.assertAlmostEqual(
                d.match(Parameter("test1", Parameter.KEYWORD_ONLY, annotation=str)),
                0.4
            )
        self.assertAlmostEqual(
            BOT_PARAM.match(
                Parameter("bot", Parameter.POSITIONAL_OR_KEYWORD, annotation=Optional[Bot])
            ), 1.5
        )
        self.assertAlmostEqual(
            SESSION_PARAM.match(
                Parameter("sess", Parameter.POSITIONAL_OR_KEYWORD, annotation=MessageSession)
            ), 1.0
        )
    
    def test_param_parser(self) -> None:
        def cmd_func(bot: Bot, /, user_id: str, content: bytes) -> None:
            pass

        sig = signature(cmd_func)
        
        parser = ParamParser.from_signature(sig)
        args, kwargs = parser.parse(new_test_message())
        self.assertEqual(args, (bot_mock,))
        self.assertEqual(kwargs, {"user_id": "user", "content": b"\"test\""})

        with self.assertRaises(KaruhaParserError):
            ParamParser.from_signature(sig, flags=ParamParserFlag.MESSAGE_DATA)
        with self.assertRaises(KaruhaParserError):
            ParamParser.from_signature(signature(lambda *args: ...))
    
    def test_function_command(self) -> None:
        with new_collection() as clt:
            called = False

            @clt.on_command(flags=ParamParserFlag.NONE)
            def test(bot: Bot, /, user_id: str, *, content: bytes) -> None:
                nonlocal called
                called = True

            self.assertIsInstance(test, FunctionCommand)
            test(bot_mock, "user", content=b"\"test\"")
            self.assertTrue(called)

            with self.assertRaises(ValueError):
                clt.add_command(test)
            
    def test_collection(self) -> None:
        reset_collection()
        set_prefix('/', '#')
        c = new_collection()
        self.assertFalse(c.activated)
        self.assertIsInstance(c.name_parser, SimpleCommandNameParser)
        self.assertEqual(c.name_parser.prefixs, ('/', '#'))  # type: ignore
        cd = get_collection()
        self.assertTrue(cd.activated)
        self.assertNotEqual(c, cd)
        with self.assertRaises(RuntimeError):
            set_prefix('!')
        
        reset_collection()
        set_prefix('/')
        set_collection_factory(lambda: c)
        self.assertIs(get_collection(), c)
        with self.assertRaises(RuntimeError):
            set_collection_factory(lambda: c)
        set_collection(cd)
        self.assertIs(get_collection(), cd)
        set_collection_factory(lambda: c, reset=True)
        self.assertIs(get_collection(), c)
