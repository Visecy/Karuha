from unittest import TestCase
from karuha.text import *
from karuha.text.convert import eval_spans, to_span_tree, spans2text, drafty2spans


example1 = DraftyMessage.model_validate_json(
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
    """.strip()
)

example2 = DraftyMessage.model_validate_json(
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
            "this is bold, code and italic, strike combined bold and italic an url: https://www.example.com/abc#fragment and another www.tinode.co this is a @mention and a #hashtag in a string second #hashtag"
        )

    def test_span(self) -> None:
        spans, attachments = eval_spans(example1)
        self.assertFalse(attachments)
        self.assertEqual(len(spans), len(example1.fmt))
        spans = to_span_tree(spans)
        self.assertEqual(len(spans), len(example1.fmt) - 2)

        spans = drafty2spans(example2)
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
