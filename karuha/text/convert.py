from typing import Callable, Dict, List, Optional, Tuple, TypeVar, Union

from ..logger import logger
from .drafty import DraftyExtend, Drafty, InlineType, ExtendType
from .textchain import BaseText, PlainText, InlineCode, TextChain, Form, _ExtensionText, _Container


def _tp_weight(tp: str) -> int:
    args: list = InlineType.__args__  # type: ignore
    if tp in args:
        return args.index(tp)
    return 0


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
        if not isinstance(other, Span):  # pragma: no cover
            return NotImplemented
        if diff := self.start - other.start:
            return diff > 0
        if diff := other.end - self.end:
            return diff > 0
        return _tp_weight(self.tp) < _tp_weight(other.tp)
    
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


def eval_spans(drafty: Drafty) -> Tuple[List[Span], List[DraftyExtend]]:
    spans = []
    attachments = []
    for i in drafty.fmt:
        if i.at < 0:
            attachments.append(drafty.ent[i.key])
            continue
        data = None
        if i.tp is None:
            if i.key < len(drafty.ent):
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
        return _converters.get(span.tp, _default_converter)(text, span)
    except Exception:  # pragma: no cover
        logger.error(f"message decode error on span {span}", exc_info=True)
        return PlainText(text=text[span.start:span.end])


def _default_converter(text: str, span: Span) -> BaseText:  # pragma: no cover
    text = text[span.start:span.end]
    logger.warn(f"unknown text {text!r}[{span.tp}]")
    return PlainText(text=text)


def _split_text(text: str, /, spans: List[Span], start: int = 0, end: int = -1) -> BaseText:
    last = start
    chain = TextChain()
    for i in spans:
        if last < i.start:
            chain += text[last:i.start]
        last = i.end
        chain += _convert(text, i)
    if end < 0:
        end = len(text)
    if last < end:
        chain += text[last:end]
    return chain.take()


def _convert_spans(text: str, spans: Optional[List[Span]], /, start: int, end: int) -> BaseText:
    if not spans:
        return PlainText(text=text[start:end])
    elif spans[0].start == start and spans[0].end == end:
        return _convert(text, spans[0])
    return _split_text(text, spans, start, end)


def _container_converter(text: str, span: Span) -> BaseText:
    return _Container.tp_map[span.tp](
        content=_convert_spans(text, span.children, span.start, span.end)
    )  # type: ignore


def _attachment_converter(text: str, span: Span) -> BaseText:
    if span.children:  # pragma: no cover
        logger.warn(f"ignore children of span {span}")
    return _ExtensionText.tp_map[span.tp](text=text[span.start:span.end], **(span.data or {}))


for i in _Container.tp_map:
    _converters[i] = _container_converter
for i in _ExtensionText.tp_map:
    _converters[i] = _attachment_converter


@converter("BR")
def BR_converter(text: str, span: Span) -> PlainText:
    return PlainText(text='\n')


@converter("CO")
def CO_converter(text: str, span: Span) -> BaseText:
    if span.children:  # pragma: no cover
        logger.warn(f"ignore children of span {span}")
    return InlineCode(text=text[span.start:span.end])


@converter("FM")
def FM_converter(text: str, span: Span) -> BaseText:
    content = _convert_spans(text, span.children, span.start, span.end)
    return Form(content=content, **(span.data or {}))


def drafty2tree_ex(drafty: Drafty) -> Tuple[List[Span], List[DraftyExtend]]:
    spans, attachments = eval_spans(drafty)
    spans = to_span_tree(spans)
    return spans, attachments


def drafty2tree(drafty: Drafty) -> List[Span]:
    return drafty2tree_ex(drafty)[0]


def tree2text(text: str, spans: List[Span]) -> BaseText:
    return _convert_spans(text, spans, 0, len(text))


def drafty2text(drafty: Drafty) -> BaseText:
    spans, attachments = drafty2tree_ex(drafty)
    text = tree2text(drafty.txt, spans)
    for i in attachments:
        text += _ExtensionText.tp_map[i.tp](**i.data)
    if isinstance(text, TextChain):
        return text.take()
    return text
