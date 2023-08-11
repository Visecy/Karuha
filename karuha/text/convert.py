import sys
from typing import Callable, Dict, List, Optional, Tuple, TypeVar, Union

from ..logger import logger
from .drafty import DraftyExtend, DraftyMessage, InlineType, ExtendType
from .textchain import BaseText, PlainText, StyleText, InlineCode, TextChain, FormText, _ExtensionText


class Span:
    __slots__ = "tp", "start", "end", "data", "children"

    def __init__(
        self,
        tp: Union[InlineType, ExtendType],
        start: int,
        end: int,
        data: Optional[dict] = None
    ) -> None:
        self.tp = tp
        self.start = start
        self.end = end
        self.data = data
        self.children: Optional[List["Span"]] = None

    def __gt__(self, other: "Span", /) -> bool:
        if not isinstance(other, Span):
            return NotImplemented
        if diff := self.start - other.start:
            return diff > 0
        if diff := other.end - self.end:
            return diff > 0
        return self.tp > other.tp
    
    def __repr__(self) -> str:
        if not self.children:
            return f"<span {self.tp} {self.start}-{self.end}>"
        return f"<span {self.tp} {self.start}-{self.end} with {len(self.children)} children>"


def to_span_tree(spans: Optional[List[Span]]) -> List[Span]:
    if not spans:
        return []
    sp_iter = iter(spans)
    last = next(sp_iter)
    tree = [last]
    for i in sp_iter:
        if i.start >= last.end:
            tree.append(i)
            last = i
        elif i.end <= last.end:
            if last.children is None:
                last.children = []
            last.children.append(i)
    
    for i in tree:
        i.children = to_span_tree(i.children)
    return tree


def eval_spans(drafty: DraftyMessage) -> Tuple[List[Span], List[DraftyExtend]]:
    spans = []
    attachments = []
    for i in drafty.fmt:
        if i.at < 0:
            attachments.append(drafty.ent[i.key])
            continue
        data = None
        if i.tp is None:
            if i.key in drafty.ent:
                ent = drafty.ent[i.key]
                tp = ent.tp
                data = ent.data
            else:
                tp = "HD"
        else:
            tp = i.tp
        spans.append(Span(tp, i.at, i.at + i.len, data))
    spans.sort()
    return spans, attachments


Converter = Callable[[str, Span], BaseText]
_T_Converter = TypeVar("_T_Converter", bound=Converter)

_converters: Dict[str, Converter] = {}


def converter(tp: Union[InlineType, ExtendType]) -> Callable[[_T_Converter], _T_Converter]:
    def inner(func: _T_Converter) -> _T_Converter:
        _converters[tp] = func
        return func
    return inner


def _convert(text: str, span: Span) -> BaseText:
    try:
        return _converters.get(span.tp, _default_convert)(text, span)
    except Exception:
        logger.error(f"message decode error on span {span}", exc_info=sys.exc_info(), stack_info=True)
        return PlainText(text=text[span.start:span.end])


def _default_convert(text: str, span: Span) -> BaseText:
    assert not span.children
    return _ExtensionText.tp_map[span.tp](text=text[span.start:span.end], **(span.data or {}))


def _split_text(text: str, /, span: List[Span]) -> List[BaseText]:
    last = 0
    raw = []
    for i in span:
        if last < i.start:
            raw.append(PlainText(text[last:i.start]))
        last = i.end
        if t := _convert(text, i):
            raw.append(t)
    if last < len(text):
        raw.append(PlainText(text[last:]))
    iter_raw = iter(raw)
    contents = [next(iter_raw)]
    for i in iter_raw:
        if isinstance(i, PlainText) and isinstance(contents[-1], PlainText):
            contents[-1].text += i.text
        elif isinstance(i, TextChain):
            contents.extend(i.contents)
        else:
            contents.append(i)
    return contents


@converter("HD")
def HD_converter(text: str, span: Span) -> PlainText:
    return PlainText(text='')


@converter("BR")
def BR_converter(text: str, span: Span) -> PlainText:
    return PlainText(text='\n')


@converter("ST")
@converter("EM")
@converter("DL")
def StyleText_converter(text: str, span: Span) -> BaseText:
    if span.tp == "ST":
        tp_key = "bold"
    elif span.tp == "EM":
        tp_key = "italic"
    elif span.tp == "DL":
        tp_key = "strikethrough"
    else:
        raise ValueError(f"invalid text type: {span.tp}")
    if not span.children:
        return StyleText(text=text[span.start:span.end], **{tp_key: True})
    
    def _filter(msg: BaseText) -> BaseText:
        if isinstance(msg, PlainText):
            msg = StyleText(text=msg.text)
        elif not isinstance(msg, StyleText):
            return msg
        setattr(msg, tp_key, True)
        return msg
    return TextChain(*filter(_filter, _split_text(text, span.children)))


@converter("CO")
def CO_converter(text: str, span: Span) -> BaseText:
    assert not span.children
    return InlineCode(text=text[span.start:span.end])


@converter("FM")
def FM_converter(text: str, span: Span) -> BaseText:
    contents = _split_text(text, span.children) if span.children is not None else ()
    return FormText(*contents, **(span.data or {}))


def drafty2spans(drafty: DraftyMessage) -> List[Span]:
    spans, _ = eval_spans(drafty)
    return to_span_tree(spans)


def spans2text(text: str, spans: List[Span]) -> BaseText:
    if not spans:
        return PlainText(text=text)
    elif spans[0].start == 0 and spans[0].end == len(text):
        return _convert(text, spans[0])
    content = _split_text(text, spans)
    if len(content) == 1:
        return content[0]
    return TextChain(*content)


def drafty2text(drafty: DraftyMessage) -> BaseText:
    return spans2text(drafty.txt, drafty2spans(drafty))
