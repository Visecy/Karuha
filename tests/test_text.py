from unittest import TestCase

from karuha.text import PlainText, Form, Drafty, drafty2tree, drafty2text
from karuha.text.textchain import File, Mention, Quote, TextChain, Bold, Hidden
from karuha.text.convert import eval_spans, to_span_tree
from karuha.event.message import MessageEvent

from .utils import bot_mock, new_test_message


example1 = Drafty.model_validate_json(
    """
{
   "txt":  "this is bold, code and italic, strike combined bold and italic an url: https://www.example.com/abc#fragment and another www.tinode.co this is a @mention and a #hashtag in a string second #hashtag",
   "fmt": [
       { "at":8, "len":4,"tp":"ST" },{ "at":14, "len":4, "tp":"CO" },{ "at":23, "len":6, "tp":"EM"},
       { "at":31, "len":6, "tp":"DL" },{ "tp":"BR", "len":1, "at":37 },{ "at":56, "len":6, "tp":"EM" },
       { "at":47, "len":15, "tp":"ST" },{ "tp":"BR", "len":1, "at":62 },{ "at":120, "len":13, "tp":"EM" },
       { "at":71, "len":36, "key":0 },{ "at":120, "len":13, "key":1 },{ "tp":"BR", "len":1, "at":133 },
       { "at":144, "len":8, "key":2 },{ "at":159, "len":8, "key":3 },{ "tp":"BR", "len":1, "at":179 },
       { "at":187, "len":8, "key":3 },{ "tp":"BR", "len":1, "at":195 }
   ],
   "ent": [
       { "tp":"LN", "data":{ "url":"https://www.example.com/abc#fragment" } },
       { "tp":"LN", "data":{ "url":"http://www.tinode.co" } },
       { "tp":"MN", "data":{ "val":"mention" } },
       { "tp":"HT", "data":{ "val":"hashtag" } }
   ]
}
    """.strip()  # noqa: E501
)

example2 = Drafty.model_validate_json(
    """
{
    "txt": "Do you agree? Yes No",
    "fmt": [
        {"len": 20, "tp": "FM"},
        {"len": 13, "tp": "ST"},
        {"at": 13, "len": 1, "tp": "BR"},
        {"at": 14, "len": 3},
        {"at": 17, "len": 1, "tp": "BR"},
        {"at": 18, "len": 2, "key": 1}
    ],
    "ent": [
        {"tp": "BN", "data": {"name": "yes", "act": "pub", "val": "oh yes!"}},
        {"tp": "BN", "data": {"name": "no", "act": "pub"}}
    ]
}
    """.strip()
)


class TestText(TestCase):
    def test_init(self) -> None:
        self.assertEqual(
            example1.txt,
            "this is bold, code and italic, strike combined bold and italic an url: "
            "https://www.example.com/abc#fragment and another www.tinode.co this "
            "is a @mention and a #hashtag in a string second #hashtag"
        )
        t = PlainText("Hello world!\n")
        self.assertEqual(str(t), "Hello world!\n")
        self.assertEqual(len(t), 13)
        self.assertEqual(str(t[0]), "H")
        self.assertEqual(str(t[1:]), "ello world!\n")
        t1 = t + "Hello world!\n"
        self.assertEqual(str(t1), "Hello world!\nHello world!\n")
        self.assertEqual(str(t), "Hello world!\n")
        empty = TextChain()
        self.assertEqual(len(empty), 0)
        self.assertEqual(str(empty), "")
        self.assertEqual(empty.to_drafty(), Drafty.from_str(' '))

    def test_span(self) -> None:
        spans, attachments = eval_spans(example1)
        self.assertFalse(attachments)
        self.assertEqual(len(spans), len(example1.fmt))
        spans = to_span_tree(spans)
        self.assertEqual(len(spans), len(example1.fmt) - 2)

        spans = drafty2tree(example2)
        # print(spans)
        self.assertEqual(len(spans), 1)

    def test_convert(self) -> None:
        txt = PlainText("Hello world!\n")
        df = txt.to_drafty()

        self.assertEqual(df.txt, "Hello world! ")
        self.assertTrue(df.fmt)
        self.assertFalse(df.ent)
        rtxt = drafty2text(df)
        self.assertEqual(txt, rtxt)

        tx1 = drafty2text(example1)
        tx2 = drafty2text(example2)
        self.assertIsInstance(tx2, Form)
        df1 = tx1.to_drafty()
        df2 = tx2.to_drafty()
        self.assertEqual(df2.txt, example2.txt)
        self.assertListEqual(df2.ent, example2.ent)
        self.assertListEqual(df2.fmt, example2.fmt)
        self.assertSetEqual(set(df1.fmt), set(example1.fmt))

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

        message = new_test_message(
            b"{\"txt\": \"test\", \"fmt\": [{\"at\": 0, \"len\": 4, \"tp\": \"ST\"}]}"
        )
        assert isinstance(message.text, Bold)
        self.assertEqual(message.text.content, PlainText("test"))
        self.assertEqual(
            message.raw_text,
            Drafty(txt="test", fmt=[{"at": 0, "len": 4, "tp": "ST"}])  # type: ignore
        )

        message = new_test_message(
            b"{\"txt\": \"test\", \"fmt\": [{\"at\": 0, \"len\": -1, \"tp\": \"ST\"}]}"
        )
        self.assertIsInstance(message.text, str)
        self.assertIsInstance(message.raw_text, str)

        message = new_test_message(
            b"{\"txt\": \"hello world\", \"fmt\": [{\"at\": 6, \"len\": 15, \"tp\": \"ST\"}]}"
        )
        assert isinstance(message.text, TextChain)
        world = message.text[1]
        assert isinstance(world, Bold)
        self.assertEqual(world.content, PlainText("world"))
        self.assertIsInstance(message.raw_text, Drafty)

        message = new_test_message(
            b"{\"txt\": \"test\", \"fmt\": [{\"at\": 0, \"len\": 4}]}"
        )
        assert isinstance(message.text, Hidden)
        self.assertEqual(message.text.content, PlainText("test"))
        self.assertIsInstance(message.raw_text, Drafty)

    def test_message_event(self) -> None:
        ev = MessageEvent(
            bot_mock,
            "", "", 0, {},
            b"\"\""
        )
        self.assertEqual(ev.text, "")
        self.assertEqual(ev.raw_text, "")
        self.assertEqual(ev.content, b"\"\"")

    def test_drafty_ops(self) -> None:
        df = Drafty.from_str("Hello")
        df = df + " world"
        self.assertEqual(str(df), "Hello world")
        df1 = "Hello" + Drafty.from_str(" world")
        self.assertEqual(df, df1)

    def test_file(self) -> None:
        f = File(
            name="test.txt",
            raw_val=b"test"  # type: ignore
        )
        self.assertEqual(f.val, "dGVzdA==")
        self.assertEqual(f.mime, "text/plain")
        
        df = Drafty.model_validate(
            {
                "ent": [
                    {
                        "data": {
                            "mime": "text/plain",
                            "name": "test.txt",
                            "size": 4,
                            "val": "dGVzdA==",
                        },
                        "tp": "EX",
                    }
                ],
                "fmt": [{"at": -1}],
            }
        )
        f = drafty2text(df)
        self.assertIsInstance(f, File)
    
    def test_quote(self) -> None:
        df = Drafty.model_validate(
            {
                "txt": "user quote textuser text",
                "fmt": [
                    {"len": 4},
                    {"at": 4, "len": 1, "tp": "BR"},
                    {"len": 15, "tp": "QQ"}
                ],
                "ent": [
                    {"tp": "MN", "data": {"val": "user_id"}}
                ]
            }
        )
        t = drafty2text(df)
        assert isinstance(t, TextChain)
        self.assertEqual(len(t), 2)
        qq = t[0]
        assert isinstance(qq, Quote) and isinstance(qq.content, TextChain)
        self.assertEqual(len(qq.content), 2)
        self.assertEqual(qq.content[0], Mention(text="user", val="user_id"))
        self.assertEqual(qq.content[1], PlainText("\nquote text"))
        self.assertEqual(t[1], PlainText("user text"))
    
    def test_split(self) -> None:
        txt = PlainText("Hello world! Hello world!")
        self.assertEqual([str(i) for i in txt.split(maxsplit=1)], "Hello world! Hello world!".split(maxsplit=1))
        tc = TextChain(*txt.split(maxsplit=2))
        self.assertEqual(len(tc), 3)
        self.assertEqual(tc[2], "Hello world!")
        self.assertEqual(tc.split(), txt.split())
        self.assertEqual(tc.split(maxsplit=2), txt.split(maxsplit=2))
        sp = tc.split(maxsplit=1)
        self.assertEqual(len(sp), 2)
        self.assertEqual(sp[0], "Hello")
        self.assertEqual(sp[1], TextChain("world!", "Hello world!"))

        tc = TextChain("Hello world!", "Hello world!")
        self.assertEqual(tc.split(), ["Hello", "world!", "Hello", "world!"])
        self.assertEqual(tc.split(maxsplit=2), ["Hello", "world!", "Hello world!"])
