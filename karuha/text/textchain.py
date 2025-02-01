import asyncio
import operator as op
import os
from abc import abstractmethod
from base64 import b64decode, b64encode
from io import BytesIO
from typing import (
    Any,
    BinaryIO,
    ClassVar,
    Dict,
    Final,
    Generator,
    Iterable,
    List,
    Literal,
    MutableMapping,
    Optional,
    Sequence,
    SupportsIndex,
    Tuple,
    Type,
    Union,
    overload,
)

from aiofiles import open as aio_open
from puremagic import from_stream, from_file
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

    def join(self, chain: Iterable[Union[str, "BaseText"]], /) -> "BaseText":
        it = iter(chain)
        try:
            first = next(it)
        except StopIteration:
            return TextChain()
        base = TextChain(first)
        for i in it:
            base += self
            if isinstance(i, str):
                i = PlainText(i)
            base += i
        return base.take()

    def startswith(self, /, prefix: str) -> bool:
        return str(self).startswith(prefix)

    def endswith(self, /, suffix: str) -> bool:
        return str(self).endswith(suffix)

    def __len__(self) -> int:
        return len(str(self))

    def __contains__(self, other: Union[str, "BaseText"]) -> bool:
        if isinstance(other, str):
            return other in str(self)
        return any(other in i if i is not self else other == i for i in self.split())

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
        while (p := self.text.find("\n", start)) != -1:
            fmt.append(DraftyFormat(at=p, len=1, tp="BR"))
            start = p + 1
        return Drafty(txt=self.text.replace("\n", " "), fmt=fmt)

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

    def __add__(self, other: Any) -> BaseText:
        if isinstance(other, PlainText):
            return PlainText(self.text + other.text)
        return super().__add__(other)

    def split(self, /, sep: Optional[str] = None, maxsplit: SupportsIndex = -1) -> List[BaseText]:
        result = []
        for p in self.text.split(sep, maxsplit):
            t = self.model_copy()
            t.text = p
            result.append(t)
        return result

    def __getitem__(self, index: Union[SupportsIndex, slice], /) -> "PlainText":
        return self.__class__(text=self.text[index])


NewLine = PlainText("\n")


class InlineCode(_Text):
    def to_drafty(self) -> Drafty:
        df = super().to_drafty()
        df.fmt.append(DraftyFormat(at=0, len=len(self), tp="CO"))
        return df


class Mention(_Text):
    type: Final[InlineType] = "MN"

    val: Optional[str] = None

    def to_drafty(self) -> Drafty:
        drafty = super().to_drafty()
        length = len(drafty.txt)
        if self.val is None:
            drafty.fmt.append(DraftyFormat(at=0, len=length, tp="MN"))
            return drafty
        key = len(drafty.ent)
        drafty.ent.append(DraftyExtend(tp="MN", data={"val": self.val}))
        drafty.fmt.append(DraftyFormat(at=0, len=length, key=key))
        return drafty


class TextChain(BaseText, Sequence):
    contents: List[BaseText]

    def __init__(self, *args: Union[BaseText, str]) -> None:
        contents = []
        for i in args:
            if isinstance(i, TextChain):
                contents.extend(i.contents)
                continue
            if isinstance(i, str):
                i = PlainText(i)
            contents.append(i)
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
        return self.contents[0] if len(self.contents) == 1 else self

    @overload
    def __getitem__(self, key: SupportsIndex, /) -> BaseText: ...
    @overload
    def __getitem__(self, key: slice, /) -> "TextChain": ...

    def __getitem__(self, key: Union[SupportsIndex, slice], /) -> BaseText:
        item = self.contents[key]
        return TextChain(*item) if isinstance(item, list) else item

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

        if self.contents:
            # merge with last item
            if isinstance(other, TextChain):
                last = None
                for i in other.contents:
                    if last is None:
                        last = self.contents.pop()
                    last = last + i
                    if isinstance(last, TextChain):
                        self.contents.extend(last.contents)
                        last = None
                if last is not None:
                    self.contents.append(last)
            elif isinstance(other, BaseText):
                last = self.contents.pop()
                last = last + other
                if isinstance(last, TextChain):
                    self.contents.extend(last.contents)
                else:
                    self.contents.append(last)
        elif isinstance(other, TextChain):
            self.contents.extend(other.contents)
        else:
            self.contents.append(other)
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
        return "".join(str(i) for i in self.contents)


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
        cls, content: bytes, *, mime: Optional[str] = None, name: Optional[str] = None, ref: Optional[str] = None, **kwds: Any
    ) -> Self:
        return cls(
            mime=mime or "text/plain",
            name=name,
            ref=ref,
            raw_val=content,  # type: ignore
            size=len(content),
            **kwds,
        )

    @classmethod
    def from_url(cls, url: str, *, mime: Optional[str] = None, name: Optional[str] = None, **kwds: Any) -> Self:
        return cls(mime=mime or "text/plain", name=name, ref=url, **kwds)

    @classmethod
    async def from_file(
        cls,
        path: Union[str, os.PathLike],
        *,
        mime: Optional[str] = None,
        name: Optional[str] = None,
        ref: Optional[str] = None,
        **kwds: Any,
    ) -> Self:
        if mime is None:
            loop = asyncio.get_running_loop()
            mime = await loop.run_in_executor(None, from_file, path, True)
        async with aio_open(path, "rb") as f:
            return cls.from_bytes(await f.read(), mime=mime, name=name or os.path.basename(path), ref=ref, **kwds)

    @classmethod
    async def analyze_bytes(cls, data: bytes, *, name: Optional[str] = None) -> Dict[str, Any]:
        return await cls.analyze_file(BytesIO(data), name=name)

    @classmethod
    async def analyze_file(cls, fp: BinaryIO, *, name: Optional[str] = None) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        mime = await loop.run_in_executor(None, from_stream, fp, True, name)
        return {"mime": mime}

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
    async def analyze_file(cls, fp: BinaryIO, *, name: Optional[str] = None) -> Dict[str, Any]:
        data = await super().analyze_file(fp, name=name)
        loop = asyncio.get_running_loop()
        size = await loop.run_in_executor(None, cls._get_image_size, fp)
        data.update(width=size[0], height=size[1])
        return data

    @staticmethod
    def _get_image_size(fp: Union[str, os.PathLike, BinaryIO]) -> Tuple[int, int]:
        from PIL.Image import open as img_open

        return img_open(fp).size


class Audio(_Attachment):
    type: Final[ExtendType] = "AU"

    mime: str = "audio/aac"
    duration: int  # duration of the record in milliseconds
    preview: str  # base64-encoded array of bytes to generate a visual preview

    VISUALIZATION_BARS: ClassVar = 96
    MAX_SAMPLES_PER_BAR: ClassVar = 10

    @classmethod
    async def analyze_file(cls, fp: BinaryIO, *, name: Optional[str] = None) -> Dict[str, Any]:
        data = await super().analyze_file(fp, name=name)
        loop = asyncio.get_running_loop()
        duration, preview = await loop.run_in_executor(None, cls._get_audio_duration_and_preview, fp)
        data.update(duration=duration, preview=preview)
        return data

    @classmethod
    def _get_audio_duration_and_preview(cls, fp: Union[str, os.PathLike, BinaryIO]) -> Tuple[int, str]:
        import soundfile as sf
        import numpy as np

        data, sample_rate = sf.read(fp)
        if len(data.shape) > 1:
            data = data[:, 0]

        total_samples = len(data)
        view_length = min(total_samples, cls.VISUALIZATION_BARS)
        total_spb = total_samples // view_length
        sampling_rate = max(1, total_spb // cls.MAX_SAMPLES_PER_BAR)

        buffer = np.zeros(view_length)

        for i in range(view_length):
            start_index = i * total_spb
            end_index = start_index + total_spb
            indices = np.arange(start_index, end_index, sampling_rate)
            valid_indices = indices[indices < total_samples]  # 确保索引不越界

            if valid_indices.size > 0:
                amplitudes = data[valid_indices] ** 2
                buffer[i] = np.sqrt(np.mean(amplitudes))

        max_val = np.max(buffer)
        if max_val > 0:
            buffer = 100 * buffer / max_val
        return (
            data.shape[0] * 1000 // sample_rate,  # type: ignore
            b64encode(buffer.tobytes()).decode("ascii"),
        )


class Video(_Attachment):
    type: Final[ExtendType] = "VD"

    mime: str = "video/webm"
    width: int
    height: int
    duration: int

    premime: Optional[str] = None
    preref: Optional[str] = None
    preview: Optional[str] = None
