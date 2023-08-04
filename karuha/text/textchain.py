"""
Instead of Drafty Text, Karuha handles text in a way
that is easier for users to read and write.
"""

from abc import abstractmethod
from base64 import encodebytes
from pathlib import Path
from pydantic import AnyHttpUrl, BaseModel, validator
from typing import Any, Dict, List, Literal, Optional, Union

from .drafty import DraftyMessage, DraftyFormat, DraftyExtend, ExtendType


class BaseText(BaseModel):
    __slots__ = []

    @abstractmethod
    def to_drafty(self) -> DraftyMessage:
        raise NotImplementedError
    
    def __len__(self) -> int:
        return len(str(self))

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self}>"
    
    @abstractmethod
    def __str__(self) -> str:
        return "<base text>"


class _PlainText(BaseText):
    text: str
    
    def to_drafty(self) -> DraftyMessage:
        start = 0
        fmt = []
        while (p := self.text.find('\n', start)) != -1:
            fmt.append(DraftyFormat(at=p, len=1, tp="BR"))
            start = p + 1
        return DraftyMessage(txt=self.text.replace('\n', ' '), fmt=fmt)
    
    def __len__(self) -> int:
        return len(self.text)
    
    def __str__(self) -> str:
        return self.text


class PlainText(_PlainText):
    def __init__(self, text: str) -> None:
        super().__init__(text=text)


class StyleText(_PlainText):
    bold: bool = False
    italic: bool = False
    strikethrough: bool = False
    
    def to_drafty(self) -> DraftyMessage:
        length = len(self)
        fmt = []
        if self.bold:
            fmt.append(DraftyFormat(at=0, len=length, tp="ST"))
        if self.italic:
            fmt.append(DraftyFormat(at=0, len=length, tp="EM"))
        if self.strikethrough:
            fmt.append(DraftyFormat(at=0, len=length, tp="DL"))
        start = 0
        while (p := self.text.find('\n', start)) != -1:
            fmt.append(DraftyFormat(at=p, len=1, tp="BR"))
            start = p + 1
        return DraftyMessage(txt=self.text.replace('\n', ' '), fmt=fmt)


class Code(_PlainText):
    def to_drafty(self) -> DraftyMessage:
        df = super().to_drafty()
        df.fmt.append(DraftyFormat(at=0, len=len(self), tp="CO"))
        return df


class _ExtensionText(_PlainText):
    type: ExtendType

    @abstractmethod
    def get_data(self) -> Dict[str, Any]:
        raise NotImplementedError
    
    def to_drafty(self) -> DraftyMessage:
        df = super().to_drafty()
        length = len(self)
        df.fmt.append(DraftyFormat(at=0 if length else -1, len=length))
        df.ent.append(DraftyExtend(tp=self.type, data=self.get_data()))
        return df


class Link(_ExtensionText):
    type: ExtendType = "LN"
    url: AnyHttpUrl

    def get_data(self) -> Dict[str, Any]:
        return {"url": self.url}
    

class Mention(_ExtensionText):
    user: str

    def get_data(self) -> Dict[str, Any]:
        return {"val": self.user}
    

class Hashtag(_ExtensionText):
    val: str

    def get_data(self) -> Dict[str, Any]:
        return {"val": self.val}


class Button(_ExtensionText):
    name: Optional[str] = None
    value: Optional[str] = None
    act: Literal["pub", "url", "note"] = "pub"
    ref: Optional[str] = None

    @validator("ref")
    def validate_ref(cls, val: Optional[str], values: Dict[str, Any]) -> Optional[str]:
        if val and values.get("act") != "url":
            raise ValueError("only button with action 'url' have field ref")
        return val

    def get_data(self) -> Dict[str, Any]:
        return self.dict(include={"name", "value", "act", "ref"}, exclude_none=True)
    
    def __str__(self) -> str:
        if self.name is None:
            return "<button>"
        if self.value:
            return f"<button {self.name}:{self.value}>"
        return f"<button {self.name}>"


class VideoCall(_ExtensionText):
    type: ExtendType = "VC"

    duration: int
    state: Literal["accepted", "busy", "finished", "disconnected", "missed", "declined"]
    incoming: bool
    aonly: bool

    def get_data(self) -> Dict[str, Any]:
        return self.dict(include={"duration", "state", "incoming", "aonly"})
    

class TextChain(BaseText):
    contents: List[BaseText]

    def __init__(self, *args: BaseText) -> None:
        super().__init__(contents=args)  # type: ignore

    def to_drafty(self) -> DraftyMessage:
        if not self.contents:
            return DraftyMessage(txt=" ")
        it = iter(self.contents)
        base = next(it).to_drafty()
        for i in it:
            base += i.to_drafty()
        return base

    def __str__(self) -> str:
        return ''.join(str(i) for i in self.contents)


class FormText(TextChain):
    su: bool = False

    def to_drafty(self) -> DraftyMessage:
        drafty = super().to_drafty()
        length = len(drafty.txt)
        if self.su:
            key = len(drafty.ent)
            drafty.ent.append(DraftyExtend(tp="FM", data={"su": True}))
            drafty.fmt.append(DraftyFormat(at=0, len=length, key=key))
        else:
            drafty.fmt.append(DraftyFormat(at=0, len=length, tp="FM"))
        return drafty


class _AttachmentMessage(_ExtensionText):
    text: str = " "
    type: ExtendType

    mime: str
    name: Optional[str] = None
    path: Optional[Path] = None
    ref: Optional[str] = None
    size: Optional[int] = None

    @staticmethod
    def read_file(path: Union[str, Path]) -> str:
        with open(path, 'rb') as f:
            return encodebytes(f.read()).decode("ascii")

    def get_val(self) -> str:
        if self.path is None:
            raise ValueError("missing resource path")
        return self.read_file(self.path)
    
    def get_data(self) -> Dict[str, Any]:
        data = self.dict(exclude={"text", "type", "path", "ref"}, exclude_none=True)
        if self.ref:
            data["ref"] = self.ref
        else:
            data["value"] = self.get_val()
        return data


class File(_AttachmentMessage):
    type: ExtendType = "EX"
    
    mime: str = "text/plain"


class Image(_AttachmentMessage):
    type: ExtendType = "IM"

    mime: str = "image/png"
    width: int
    height: int

    def __str__(self) -> str:
        if self.path:
            return f"<image at {self.path}>"
        else:
            return f"<image from {self.ref}>"


class Audio(_AttachmentMessage):
    type: ExtendType = "AU"

    mime: str = "audio/aac"
    duration: int
    preview: bytes

    def get_data(self) -> Dict[str, Any]:
        data = super().get_data()
        data["preview"] = encodebytes(data["preview"]).decode("ascii")
        return data


class Video(_AttachmentMessage):
    type: ExtendType = "VD"

    mime: str = "video/webm"
    width: int
    height: int
    duration: int

    premime: Optional[str] = None
    preref: Optional[str] = None
    prepath: Optional[Path] = None
    
    def get_val(self) -> str:
        if self.path is None:
            raise ValueError("missing resource path")
        return self.read_file(self.path)
