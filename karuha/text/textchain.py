import mimetypes
import os
import operator as op
from abc import abstractmethod
from base64 import b64decode, b64encode
from typing import (Any, ClassVar, Dict, Final, Generator, List, Literal,
                    MutableMapping, Optional, Sequence, SupportsIndex, Type,
                    Union, overload)

from aiofiles import open as aio_open
from pydantic import AnyHttpUrl, BaseModel, model_validator
from typing_extensions import Self

from .drafty import Drafty, DraftyExtend, DraftyFormat, ExtendType, InlineType


class BaseText(BaseModel):
    __slots__ = []

    @abstractmethod
    def to_drafty(self) -> Drafty:
        raise NotImplementedError

    def split(self, /, sep: Optional[str] = None, maxsplit: SupportsIndex = -1) -> List["BaseText"]:
        return [self]

    def startswith(self, /, prefix: str) -> bool:
        return str(self).startswith(prefix)

    def endswith(self, /, suffix: str) -> bool:
        return str(self).endswith(suffix)

    def __len__(self) -> int:
        return len(str(self))

    def __contains__(self, other: Union[str, "BaseText"]) -> bool:
        if isinstance(other, str):
            return other in str(self)
        return any(
            other in i if i is not self else other == i
            for i in self.split()
        )

    def __add__(self, other: Union[str, "BaseText"]) -> "BaseText":
        if not other:
            return self
        if isinstance(other, str):
            other = PlainText(other)
        if not self:
            return other
        if not isinstance(other, TextChain) and isinstance(other, BaseText):
            return TextChain(self, other)
        return NotImplemented

    def __radd__(self, other: str) -> "BaseText":
        if not other:
            return self
        if isinstance(other, str):
            return TextChain(PlainText(other), self)
        return NotImplemented

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {str(self)!r}>"

    @abstractmethod
    def __str__(self) -> str:
        return "unknown"


class _Text(BaseText):
    text: str
    
    def to_drafty(self) -> Drafty:
        start = 0
        fmt = []
        while (p := self.text.find('\n', start)) != -1:
            fmt.append(DraftyFormat(at=p, len=1, tp="BR"))
            start = p + 1
        return Drafty(txt=self.text.replace('\n', ' '), fmt=fmt)

    def __eq__(self, __value: Any) -> bool:
        if isinstance(__value, str):
            return self.text == __value
        return super().__eq__(__value)
    
    def __len__(self) -> int:
        return len(self.text)
    
    def __str__(self) -> str:
        return self.text


class PlainText(_Text):
    def __init__(self, text: str) -> None:
        super().__init__(text=text)
    
    def split(self, /, sep: Optional[str] = None, maxsplit: SupportsIndex = -1) -> List[BaseText]:
        result = []
        for p in self.text.split(sep, maxsplit):
            t = self.model_copy()
            t.text = p
            result.append(t)
        return result

    def __iadd__(self, other: Union[str, BaseText]) -> BaseText:
        if not isinstance(other, (str, PlainText)):
            return NotImplemented
        self.text += other if isinstance(other, str) else other.text
        return self
    
    def __getitem__(self, index: Union[SupportsIndex, slice], /) -> "PlainText":
        return self.__class__(text=self.text[index])


NewLine = PlainText("\n")


class InlineCode(_Text):
    def to_drafty(self) -> Drafty:
        df = super().to_drafty()
        df.fmt.append(DraftyFormat(at=0, len=len(self), tp="CO"))
        return df


class TextChain(BaseText, Sequence):
    contents: List[BaseText]

    def __init__(self, *args: Union[BaseText, str]) -> None:
        contents = [
            PlainText(t) if isinstance(t, str) else t
            for t in args if t
        ]
        super().__init__(contents=contents)  # type: ignore
    
    def to_drafty(self) -> Drafty:
        if not self.contents:
            return Drafty(txt=" ")
        it = iter(self.contents)
        base = next(it).to_drafty()
        for i in it:
            base += i.to_drafty()
        return base
    
    def split(self, /, sep: Optional[str] = None, maxsplit: SupportsIndex = -1) -> List[BaseText]:
        if not self:
            return []
        maxsplit = op.index(maxsplit)
        remain_count = maxsplit - len(self.contents) + 1
        if maxsplit >= 0 and remain_count < 0:
            content = self.contents[:maxsplit]
            content.append(self[maxsplit:])
            return content
    
        result = []
        for i in self.contents:
            if maxsplit >= 0 and remain_count < 0:
                result.append(i)
            else:
                sp = i.split(sep, remain_count)
                result.extend(sp)
                remain_count -= len(sp) - 1
        return result
    
    def take(self) -> BaseText:
        if len(self.contents) == 1:
            return self.contents[0]
        return self
    
    @overload
    def __getitem__(self, key: SupportsIndex, /) -> BaseText: ...
    @overload
    def __getitem__(self, key: slice, /) -> "TextChain": ...

    def __getitem__(self, key: Union[SupportsIndex, slice], /) -> BaseText:
        item = self.contents[key]
        if isinstance(item, list):
            return TextChain(*item)
        return item

    def __iter__(self) -> Generator[BaseText, None, None]:
        yield from self.contents
    
    def __len__(self) -> int:
        return len(self.contents)
    
    def __add__(self, other: Union[str, BaseText]) -> Self:
        if not other:
            return self
        elif not isinstance(other, (str, BaseText, TextChain)):
            return NotImplemented
        chain = self.model_copy()
        chain += other
        return chain
    
    def __iadd__(self, other: Union[str, BaseText]) -> Self:
        if not other:  # filter empty text like PlainText('')
            return self
        elif isinstance(other, str):
            other = PlainText(other)
        elif not isinstance(other, BaseText):
            return NotImplemented
        
        if not self.contents:
            # fast branch, no optimization
            if isinstance(other, TextChain):
                self.contents.extend(other.contents)
            else:
                self.contents.append(other)
        else:
            # merge with last item
            last = self.contents[-1]
            if isinstance(other, TextChain):
                contents_iter = iter(other.contents)
                for i in contents_iter:
                    last += i
                    if isinstance(last, TextChain):
                        self.contents.append(i)
                        break
                    else:
                        self.contents[-1] = last
                self.contents.extend(contents_iter)
            elif isinstance(other, BaseText):
                last += other
                if isinstance(last, TextChain):
                    self.contents.append(other)
                else:
                    self.contents[-1] = last
        return self
    
    def __radd__(self, other: Union[str, BaseText]) -> Self:
        if not other:
            return self
        chain = self.model_copy()
        if isinstance(other, str):
            chain.contents.insert(0, PlainText(other))
        elif isinstance(other, BaseText):
            chain.contents.insert(0, other)
        else:
            return NotImplemented
        return chain

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.contents}>"

    def __str__(self) -> str:
        return ''.join(str(i) for i in self.contents)


class _Container(BaseText):
    tp_map: ClassVar[Dict[str, Type["_Container"]]] = {}

    type: InlineType
    content: BaseText
    
    def to_drafty(self) -> Drafty:
        df = self.content.to_drafty()
        df.fmt.insert(0, DraftyFormat(at=0, len=len(df.txt), tp=self.type))
        return df
    
    @classmethod
    def new(cls, text: Union[str, BaseText]) -> Self:
        if isinstance(text, str):
            text = PlainText(text)
        return cls(content=text)  # type: ignore
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.content!r}>"
    
    def __str__(self) -> str:
        return str(self.content)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        tp = getattr(cls, "type", cls.model_fields["type"].default)
        if isinstance(tp, str):
            cls.tp_map[tp] = cls


class Bold(_Container):
    type: Final[InlineType] = "ST"


class Italic(_Container):
    type: Final[InlineType] = "EM"


class Strikethrough(_Container):
    type: Final[InlineType] = "DL"


class Highlight(_Container):
    type: Final[InlineType] = "HL"


class Hidden(_Container):
    type: Final[InlineType] = "HD"


class Row(_Container):
    type: Final[InlineType] = "RW"


class Quote(_Container):
    type: Final[InlineType] = "QQ"

    @property
    def mention(self) -> Optional["Mention"]:
        if not isinstance(self.content, TextChain) or not self.content:
            return
        mn = self.content[0]
        assert isinstance(mn, Mention)
        return mn

    @property
    def quote_content(self) -> Optional[BaseText]:
        if not isinstance(self.content, TextChain):
            return
        elif len(self.content) == 2 and isinstance(self.content[1], PlainText):
            return PlainText(str(self.content[1])[1:])
        elif len(self.content) == 3:
            return self.content[2]


class Form(_Container):
    type: Final[InlineType] = "FM"

    su: bool = False

    def to_drafty(self) -> Drafty:
        if not self.su:
            return super().to_drafty()
        drafty = self.content.to_drafty()
        length = len(drafty.txt)
        key = len(drafty.ent)
        drafty.ent.append(DraftyExtend(tp="FM", data={"su": True}))
        drafty.fmt.append(DraftyFormat(at=0, len=length, key=key))
        return drafty


class _ExtensionText(_Text):
    tp_map: ClassVar[Dict[str, Type["_ExtensionText"]]] = {}

    type: ExtendType

    @abstractmethod
    def get_data(self) -> Dict[str, Any]:
        raise NotImplementedError
    
    def to_drafty(self) -> Drafty:
        df = super().to_drafty()
        length = len(self)
        df.fmt.append(DraftyFormat(at=0 if length else -1, len=length))
        df.ent.append(DraftyExtend(tp=self.type, data=self.get_data()))
        return df
    
    def __bool__(self) -> bool:
        return bool(self.text or self.get_data())
    
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        tp = getattr(cls, "type", cls.model_fields["type"].default)
        if isinstance(tp, str):
            cls.tp_map[tp] = cls


class Link(_ExtensionText):
    type: Final[ExtendType] = "LN"
    url: AnyHttpUrl

    def get_data(self) -> Dict[str, Any]:
        return {"url": self.url}


class Mention(_ExtensionText):
    type: Final[ExtendType] = "MN"

    val: str

    def get_data(self) -> Dict[str, Any]:
        return {"val": self.val}


class Hashtag(_ExtensionText):
    type: Final[ExtendType] = "HT"

    val: str

    def get_data(self) -> Dict[str, Any]:
        return {"val": self.val}


class Button(_ExtensionText):
    type: Final[ExtendType] = "BN"

    name: Optional[str] = None
    val: Optional[str] = None
    act: Literal["pub", "url", "note"] = "pub"
    ref: Optional[str] = None

    @model_validator(mode="after")
    def validate_ref(self) -> Self:
        if self.ref and self.act != "url":
            raise ValueError("only button with action 'url' have field ref")
        return self

    def get_data(self) -> Dict[str, Any]:
        return self.model_dump(include={"name", "val", "act", "ref"}, exclude_none=True)
    
    def __repr__(self) -> str:
        if self.name is None:
            return f"<button {self.text!r}>"
        if self.val:
            return f"<button {self.text!r} ({self.name}:{self.val})>"
        return f"<button {self.text!r} ({self.name})>"


class VideoCall(_ExtensionText):
    type: ExtendType = "VC"

    duration: int
    state: Literal["accepted", "busy", "finished", "disconnected", "missed", "declined"]
    incoming: bool
    aonly: bool

    def get_data(self) -> Dict[str, Any]:
        return self.dict(include={"duration", "state", "incoming", "aonly"})


class _Attachment(_ExtensionText):
    text: str = ""
    type: ExtendType

    mime: str
    name: Optional[str] = None
    val: Optional[Any] = None
    ref: Optional[str] = None
    size: Optional[int] = None

    @classmethod
    def from_bytes(
            cls,
            content: bytes,
            *,
            mime: Optional[str] = None,
            name: Optional[str] = None,
            ref: Optional[str] = None,
            **kwds: Any
    ) -> Self:
        return cls(  # type: ignore
            mime=mime or "text/plain",
            name=name,
            ref=ref,
            raw_val=content,  # type: ignore
            size=len(content),
            **kwds
        )

    @classmethod
    async def from_file(
            cls,
            path: Union[str, os.PathLike],
            *,
            mime: Optional[str] = None,
            name: Optional[str] = None,
            ref: Optional[str] = None,
            **kwds: Any
    ) -> Self:
        mime = mime or mimetypes.guess_type(path)[0]
        async with aio_open(path, "rb") as f:
            return cls.from_bytes(
                await f.read(),
                mime=mime, name=name or os.path.basename(path),
                ref=ref,
                **kwds
            )

    async def save(self, path: Union[str, os.PathLike, None] = None) -> None:
        path = path or self.name
        if path is None:
            raise ValueError("no path provided")
        value = self.raw_val
        if value is None:
            raise ValueError("no vaild file content")
        async with aio_open(path, "wb") as f:
            await f.write(value)

    @property
    def raw_val(self) -> Optional[bytes]:
        if not self.val:
            return
        return b64decode(self.val)

    @raw_val.setter
    def raw_val(self, value: Optional[bytes]) -> None:
        if value is None:
            self.val = None
            return
        self.val = b64encode(value).decode("ascii")

    @model_validator(mode="before")  # type: ignore
    def convert_raw(cls, data: Any) -> Any:
        if isinstance(data, MutableMapping):
            for k, v in tuple(data.items()):
                if isinstance(k, str) and isinstance(v, bytes) and k.startswith("raw_"):
                    data.pop(k)
                    data[k[4:]] = b64encode(v).decode("ascii")
        return data

    def get_data(self) -> Dict[str, Any]:
        return self.model_dump(exclude={"text", "type"}, exclude_none=True)

    def __repr__(self) -> str:
        name = self.__class__.__name__
        if self.ref:
            return f"<{name} from {self.ref}>"
        elif self.val:
            value = self.val
            if len(value) < 20:
                return f"<{name} {value}>"
            return f"<{name} {value[:15]}..{value[-3:]}>"
        return f"<{name}>"


class File(_Attachment):
    type: Final[ExtendType] = "EX"
    
    mime: str = "text/plain"


class Image(_Attachment):
    type: Final[ExtendType] = "IM"

    mime: str = "image/png"
    width: int
    height: int

    @classmethod
    async def from_file(
            cls,
            path: Union[str, os.PathLike],
            *,
            mime: Optional[str] = None,
            name: Optional[str] = None,
            ref: Optional[str] = None,
            width: Optional[int] = None,
            height: Optional[int] = None,
            **kwds: Any
    ) -> Self:
        if width and height:
            return await super().from_file(
                path, mime=mime, name=name, ref=ref,
                **kwds
            )
        from io import BytesIO

        from PIL.Image import open as img_open
        mime = mime or mimetypes.guess_type(path)[0]
        async with aio_open(path, "rb") as f:
            content = await f.read()
        img = img_open(BytesIO(content))
        return cls.from_bytes(
            content,
            mime=mime, name=name or os.path.basename(path),
            ref=ref,
            width=img.width, height=img.height,
            **kwds
        )


class Audio(_Attachment):
    type: Final[ExtendType] = "AU"

    mime: str = "audio/aac"
    duration: int
    preview: str


class Video(_Attachment):
    type: Final[ExtendType] = "VD"

    mime: str = "video/webm"
    width: int
    height: int
    duration: int

    premime: Optional[str] = None
    preref: Optional[str] = None
    preview: Optional[str] = None
