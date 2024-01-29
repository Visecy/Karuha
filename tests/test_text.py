from unittest import TestCase

from karuha.text import PlainText, Form, Drafty, drafty2tree, drafty2text
from karuha.text.textchain import TextChain
from karuha.text.convert import eval_spans, to_span_tree
from karuha.event import MessageEvent

from .utils import bot_mock


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
        self.assertLessEqual(df2.fmt, example2.fmt)
        # print(df1.model_dump_json(indent=4))
        self.assertSetEqual(set(df1.fmt), set(example1.fmt))
    
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
