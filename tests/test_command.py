from inspect import signature
from pathlib import Path
from typing import List, Optional
from pydantic import TypeAdapter, ValidationError
from typing_extensions import Annotated
from unittest import TestCase

from pydantic_core import to_json

from karuha.bot import Bot
from karuha.text import PlainText, Drafty, Message, Head
from karuha.session import BaseSession
from karuha.command.rule import rule
from karuha.command.collection import (
    add_sub_collection,
    get_collection,
    new_collection,
    remove_sub_collection,
    reset_collection,
    set_collection,
    set_collection_factory,
    set_prefix,
)
from karuha.command.command import FunctionCommand
from karuha.command.parser import SimpleCommandParser
from karuha.exception import KaruhaCommandError, KaruhaHandlerInvokerError
from karuha.text.textchain import Mention, NewLine, Quote, TextChain
from karuha.utils.invoker import ChainHandlerInvoker, DictHandlerInvoker
from karuha.utils.argparse import Argument, Arg, get_argument, build_parser

from .utils import TEST_TOPIC, TEST_UID, bot_mock, new_test_message, new_test_command_message


class TestCommand(TestCase):
    def test_name_parser(self) -> None:
        simple_parser = SimpleCommandParser(["!"])
        message0 = new_test_message(b"!test")
        self.assertEqual(simple_parser.parse(message0), ("test", []))
        message1 = new_test_message(b'"!test"')
        self.assertEqual(simple_parser.parse(message1), ("test", []))
        message2 = new_test_message(b'{"txt": "test"}')
        self.assertIsNone(simple_parser.parse(message2))
        message3 = new_test_message(b'"!!test test test test"')
        self.assertEqual(simple_parser.parse(message3), ("!test", [PlainText("test"), PlainText("test"), PlainText("test")]))
        message4 = new_test_message(b'"!"')
        self.assertEqual(simple_parser.parse(message4), ("", []))
        message5 = new_test_message(b'""')
        self.assertIsNone(simple_parser.parse(message5))

    def test_invoker(self) -> None:
        invoker1 = DictHandlerInvoker({"foo": 114})
        invoker2 = DictHandlerInvoker({"bar": 514})
        invoker = ChainHandlerInvoker(invoker1, invoker2)
        self.assertEqual(invoker1.call_handler(lambda foo: foo), 114)
        with self.assertRaises(KaruhaHandlerInvokerError):
            invoker1.call_handler(lambda foo, bar: foo + bar)
        self.assertEqual(invoker.call_handler(lambda foo, bar: foo + bar), 114 + 514)
        with self.assertRaises(KaruhaHandlerInvokerError):
            invoker.call_handler(lambda foo, bar, unknown: foo + bar + unknown)

        invoker = DictHandlerInvoker({"args": ("foo", "bar")})
        self.assertEqual(invoker.call_handler(lambda *args: args), ("foo", "bar"))

        invoker = DictHandlerInvoker({"kwds": {"foo": 114, "bar": 514}})
        self.assertEqual(invoker.call_handler(lambda **kwds: kwds), {"foo": 114, "bar": 514})

    def test_cmd_invoker(self) -> None:
        def cmd_meta(
            bot: Bot,
            message: Message,
            /,
            user_id: Optional[str],
            content: bytes,
            argc: int,
            argv: List[str],
            undefined: None = None,
        ) -> int:
            return 114

        sig = signature(cmd_meta)
        msg = new_test_command_message()
        args, kwargs = msg.extract_handler_params(sig)
        self.assertEqual(args, [bot_mock, msg])
        self.assertEqual(kwargs, {"user_id": TEST_UID, "content": b'"test"', "argc": 0, "argv": [], "undefined": None})

        def cmd_head(undefined: Head[None], test: Head[Optional[int]] = None) -> None:
            self.assertEqual(test, 1)
            self.assertIsNone(undefined)

        msg = Message.new(bot_mock, "test", "usr_test", 0, {"test": "1"}, b'"test"')
        msg.call_handler(cmd_head)

        def cmd_text(text: PlainText, raw_text: Drafty) -> None:
            pass

        with self.assertRaises(KaruhaHandlerInvokerError):
            msg.call_handler(cmd_text)
        sig = signature(cmd_text)
        args, kwargs = new_test_command_message(b'{"txt": "test"}').extract_handler_params(sig)
        self.assertEqual(args, [])
        self.assertEqual(kwargs, {"text": PlainText("test"), "raw_text": Drafty(txt="test")})

        def cmd_plain_text(text: str, raw_text: str) -> None:
            pass

        sig = signature(cmd_plain_text)
        args, kwargs = new_test_command_message(b'{"txt": "test"}').extract_handler_params(sig)
        self.assertEqual(args, [])
        self.assertEqual(kwargs, {"text": "test", "raw_text": "test"})

        def cmd_no_annotation(text, /, raw_text, content, undefined=None) -> None:
            pass

        sig = signature(cmd_no_annotation)
        args, kwargs = new_test_command_message(b'{"txt": "test"}').extract_handler_params(sig)
        self.assertEqual(args, [PlainText("test")])
        self.assertEqual(kwargs, {"raw_text": Drafty(txt="test"), "content": b'{"txt": "test"}', "undefined": None})

    def test_function_command(self) -> None:
        with new_collection() as clt:
            called = False

            with self.assertRaises(KaruhaCommandError):
                clt["test"]

            @clt.on_command("test")
            def test(bot: Bot, /, message: Message, *, text: PlainText) -> None:
                """
                Test help
                """
                nonlocal called
                called = True

            self.assertIsInstance(test, FunctionCommand)
            self.assertIs(clt["test"], test)
            test(bot_mock, new_test_message(), text=PlainText("test"))
            self.assertTrue(called)
            self.assertEqual(test.format_help(), "test - Test help")
            test.alias += ("test1",)
            self.assertEqual(test.format_help(), "test (alias: test1) - Test help")
            test.__doc__ = None
            self.assertEqual(test.format_help(), "test (alias: test1)")
            test.alias = ()
            self.assertEqual(test.format_help(), "test")

            with self.assertRaises(ValueError):
                clt.add_command(test)

    def test_collection(self) -> None:
        reset_collection()
        set_prefix("/", "#")
        c = new_collection()
        self.assertFalse(c.activated)
        self.assertIsInstance(c.name_parser, SimpleCommandParser)
        self.assertEqual(c.name_parser.prefixs, ("/", "#"))  # type: ignore
        cd = get_collection()
        self.assertTrue(cd.activated)
        self.assertNotEqual(c, cd)
        with self.assertRaises(RuntimeError):
            set_prefix("!")

        reset_collection()
        set_prefix("/")
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
        c.add_command(FunctionCommand.from_function(lambda bot: ..., name="test"))

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
        rt = rule(topic=TEST_TOPIC)
        self.assertEqual(rt.match(msg), 1.0)
        rs = rule(topic=TEST_TOPIC, seq_id=1)
        self.assertEqual(rs.match(msg), 1.0)
        ru = rule(user_id=TEST_UID)
        self.assertEqual(ru.match(msg), 1.0)
        rr = rule(regex=r"W.+d")
        self.assertEqual(rr.match(msg), 1.0)
        ra = rk & rt
        self.assertAlmostEqual(ra.match(msg), 1.0)
        rn = ~rt
        self.assertAlmostEqual(rn.match(msg), 0.0)
        ro = rk | rn
        self.assertAlmostEqual(ro.match(msg), 1.0)
        rq = rule(quote=True)
        self.assertEqual(rq.match(msg), 0.0)

        msg = Message.new(
            bot_mock,
            "test",
            "usr",
            1,
            {"reply": "114"},
            to_json(
                TextChain(
                    Quote(content=TextChain(Mention(text="@user", val=TEST_UID), NewLine, "Quote content ...")), "Hello world!"
                ).to_drafty()
            ),
        )
        self.assertEqual(rq.match(msg), 1.0)
        rq1 = rule(quote=114)
        self.assertEqual(rq1.match(msg), 1.0)
        rq2 = rule(quote=514)
        self.assertEqual(rq2.match(msg), 0.0)
        rm = rule(mention=TEST_UID)
        self.assertEqual(rm.match(msg), 1.0)
        rm1 = rule(mention="114514")
        self.assertEqual(rm1.match(msg), 0.0)
        r2m = rule(to_me=True)
        self.assertEqual(r2m.match(msg), 1.0)
        rb = rule(bot=bot_mock)
        self.assertEqual(rb.match(msg), 1.0)
        rh = rule(has_head="reply")
        self.assertEqual(rh.match(msg), 1.0)
        rh1 = rule(has_head="quote")
        self.assertEqual(rh1.match(msg), 0.0)

    def test_argument(self) -> None:
        arg = Arg[str, "-v", "--version"]
        arg_ins = get_argument(arg)
        assert arg_ins is not None
        self.assertEqual(arg_ins.args, ("-v", "--version"))
        self.assertEqual(arg_ins.kwargs, {"type": str})

        arg = Arg[str, "-v", "--version", {}]
        self.assertEqual(get_argument(arg), arg_ins)

        arg = Arg[str, "-v", "--version", Argument(type=str)]
        self.assertEqual(get_argument(arg), arg_ins)

        arg = Annotated[str, Argument("-v", "--version", type=str)]
        self.assertEqual(get_argument(arg), arg_ins)

    def test_argument_validate(self) -> None:
        ta = TypeAdapter(Argument)
        self.assertEqual(ta.validate_python(Argument("-v", "--version", type=str)), Argument("-v", "--version", type=str))
        with self.assertRaises(ValidationError):
            ta.validate_python("str")

        ta = TypeAdapter(Arg[str, "-v", "--version"])
        with self.assertRaises(ValidationError):
            ta.validate_python(Argument("-v", "--version", type=str))
        self.assertEqual(ta.validate_python("str"), "str")

        def example(
            path: Arg[str, Argument(help="Input path")],
            timeout: Arg[int, "-t"] = 10,  # noqa: F821
            *,
            force: Arg[bool, "-f", "--force"] = False,  # noqa: F821
        ) -> str:
            self.assertEqual(timeout, 20)
            self.assertTrue(force)
            return path

        invoker = DictHandlerInvoker({"argv": ("/tmp", "-t", "20", "-f"), "session": BaseSession(bot_mock, TEST_TOPIC)})
        self.assertEqual(invoker.call_handler(example), "/tmp")

    def test_build_parser(self) -> None:
        def example(
            path: Arg[str, Argument(help="Input path")],
            timeout: Arg[int, "--timeout"] = 10,  # noqa: F821
            *,
            force: bool = False,
        ) -> None: ...

        parser = build_parser(example, unannotated_mode="autoconvert")
        self.assertEqual(
            parser.parse_known_args(["/tmp", "--force", "--timeout", "20"])[0].__dict__,
            {"path": "/tmp", "force": True, "timeout": 20},
        )

        with self.assertRaises(TypeError):
            build_parser(example, unannotated_mode="strict")

        parser = build_parser(example, unannotated_mode="ignore")
        self.assertEqual(parser.parse_known_args(["/tmp", "--force"])[0].__dict__, {"path": "/tmp", "timeout": 10})

        def example2(
            path: Arg[str, Argument(help="Input path", type=Path)],
            *args: Arg[str, Argument(help="Extra arguments")],
        ) -> None: ...

        parser = build_parser(example2, unannotated_mode="strict")
        self.assertEqual(
            parser.parse_known_args(["/tmp", "foo", "bar"])[0].__dict__, {"path": Path("/tmp"), "args": ["foo", "bar"]}
        )
