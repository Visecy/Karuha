from inspect import Parameter, signature
from unittest import TestCase

from karuha.bot import Bot
from karuha.text import Message, Drafty, PlainText
from karuha.command.parser import ParamParserFlag, SimpleCommandNameParser, MetaParamDispatcher, ParamParser

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
        d = MetaParamDispatcher("test", str, lambda d, x: d.name, ParamParserFlag.MESSAGE_DATA)
        self.assertAlmostEqual(
            d.match(Parameter("test", Parameter.POSITIONAL_ONLY, annotation=str)),
            1.8
        )
        self.assertAlmostEqual(
            d.match(Parameter("test", Parameter.KEYWORD_ONLY, annotation=str, default="test")),
            2.0
        )
        self.assertAlmostEqual(
            d.match(Parameter("test", Parameter.KEYWORD_ONLY)),
            1.2
        )
        self.assertAlmostEqual(
            d.match(Parameter("test1", Parameter.KEYWORD_ONLY, annotation=str)),
            0.8
        )
    
    def test_param_parser(self) -> None:
        def cmd_func(bot: Bot, /, user_id: str, content: bytes) -> None:
            pass

        sig = signature(cmd_func)
        
        parser = ParamParser.from_signature(sig)
        args, kwargs = parser.parse(new_test_message())
        self.assertEqual(args, (bot_mock,))
        self.assertEqual(kwargs, {"user_id": "user", "content": b"\"test\""})
