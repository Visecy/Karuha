from inspect import Parameter, signature
from typing import List, Optional, Tuple
from unittest import TestCase

from karuha.bot import Bot
from karuha.text import BaseText, PlainText, Drafty, Message
from karuha.command.collection import (add_sub_collection, get_collection, new_collection, remove_sub_collection,
                                       reset_collection, set_collection,
                                       set_collection_factory, set_prefix)
from karuha.command.command import CommandMessage, FunctionCommand, ParamFunctionCommand
from karuha.command.parser import (BOT_PARAM, SESSION_PARAM,
                                   MetaParamDispatcher, ParamDispatcher, ParamParser,
                                   ParamParserFlag, SimpleCommandParser)
from karuha.command.session import MessageSession
from karuha.exception import KaruhaCommandError, KaruhaParserError

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
            ), 0.8
        )

        message = new_test_command_message()
        self.assertEqual(
            ParamDispatcher.dispatch(Parameter("name", Parameter.POSITIONAL_ONLY))(message),
            "test"
        )
        self.assertEqual(
            ParamDispatcher.dispatch(Parameter("name", Parameter.POSITIONAL_ONLY, annotation=str))(message),
            "test"
        )
        self.assertEqual(
            ParamDispatcher.dispatch(Parameter("argc", Parameter.POSITIONAL_ONLY))(message),
            0
        )
        self.assertEqual(
            ParamDispatcher.dispatch(Parameter("argv", Parameter.POSITIONAL_ONLY))(message),
            ()
        )
        self.assertEqual(
            ParamDispatcher.dispatch(Parameter("argv", Parameter.POSITIONAL_ONLY, annotation=list))(message),
            []
        )
        message = CommandMessage.from_message(
            message,
            FunctionCommand("test", lambda: None),
            new_collection(),
            "test",
            [PlainText("test")]
        )
        self.assertEqual(
            ParamDispatcher.dispatch(Parameter("argc", Parameter.POSITIONAL_ONLY, annotation=int))(message),
            1
        )
        self.assertEqual(
            ParamDispatcher.dispatch(Parameter("argv", Parameter.POSITIONAL_ONLY, annotation=List[str]))(message),
            ["test"]
        )
        self.assertEqual(
            ParamDispatcher.dispatch(Parameter("argv", Parameter.POSITIONAL_ONLY, annotation=List[BaseText]))(message),
            [PlainText("test")]
        )
        self.assertEqual(
            ParamDispatcher.dispatch(Parameter("argv", Parameter.POSITIONAL_ONLY, annotation=Tuple[str, ...]))(message),
            ("test",)
        )
        self.assertEqual(
            ParamDispatcher.dispatch(Parameter("argv", Parameter.POSITIONAL_ONLY, annotation=Tuple[BaseText, ...]))(message),
            (PlainText("test"),)
        )
    
    def test_param_parser(self) -> None:
        def cmd_meta(bot: Bot, message: Message, /, user_id: Optional[str], content: bytes, argv: list) -> None:
            pass

        sig = signature(cmd_meta)
        parser = ParamParser.from_signature(sig)
        msg = new_test_command_message()
        args, kwargs = parser.parse(msg)
        self.assertEqual(args, (bot_mock, msg))
        self.assertEqual(kwargs, {"user_id": "user", "content": b"\"test\"", "argv": []})

        with self.assertRaises(KaruhaParserError):
            ParamParser.from_signature(sig, flags=ParamParserFlag.MESSAGE_DATA)
        with self.assertRaises(KaruhaParserError):
            ParamParser.from_signature(signature(lambda *message: ...))
        
        def cmd_text(text: PlainText, raw_text: Drafty) -> None:
            pass

        sig = signature(cmd_text)
        parser = ParamParser.from_signature(sig, flags=ParamParserFlag.MESSAGE_DATA)
        with self.assertRaises(KaruhaParserError):
            parser.parse(new_test_command_message())
        args, kwargs = parser.parse(new_test_command_message(b"{\"txt\": \"test\"}"))
        self.assertEqual(args, ())
        self.assertEqual(kwargs, {"text": PlainText("test"), "raw_text": Drafty(txt="test")})

        def cmd_plain_text(text: str, raw_text: str) -> None:
            pass

        sig = signature(cmd_plain_text)
        parser = ParamParser.from_signature(sig, flags=ParamParserFlag.MESSAGE_DATA)
        args, kwargs = parser.parse(new_test_command_message(b"{\"txt\": \"test\"}"))
        self.assertEqual(args, ())
        self.assertEqual(kwargs, {"text": "test", "raw_text": "test"})

        def cmd_no_annotation(text, /, raw_text, content) -> None:
            pass

        sig = signature(cmd_no_annotation)
        parser = ParamParser.from_signature(sig, flags=ParamParserFlag.META)
        args, kwargs = parser.parse(new_test_command_message(b"{\"txt\": \"test\"}"))
        self.assertEqual(args, (PlainText("test"),))
        self.assertEqual(kwargs, {"raw_text": Drafty(txt="test"), "content": b"{\"txt\": \"test\"}"})
    
    def test_function_command(self) -> None:
        with new_collection() as clt:
            called = False

            with self.assertRaises(KaruhaCommandError):
                clt["test"]

            @clt.on_command("test", flags=ParamParserFlag.NONE)
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
