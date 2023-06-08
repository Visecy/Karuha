"""
Instead of Drafty Text, Karuha handles text in a way
that is easier for users to read and write.
"""

from abc import abstractmethod
from base64 import encodebytes
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Literal, Optional

from karuha.text.drafty import DraftyMessage

from ..config import BaseModel
from .drafty import DraftyMessage, DraftyFormat, DraftyExtend


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
    

class PlainText(BaseText):
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    strikethrough: bool = False
    
    def to_drafty(self) -> DraftyMessage:
        length = len(self.text)
        fmt = []
        if self.bold:
            fmt.append(DraftyFormat(at=0, len=length, tp="ST"))
        if self.italic:
            fmt.append(DraftyFormat(at=0, len=length, tp="EM"))
        if self.code:
            fmt.append(DraftyFormat(at=0, len=length, tp="CO"))
        if self.strikethrough:
            fmt.append(DraftyFormat(at=0, len=length, tp="DL"))
        start = 0
        while (p := self.text.find('\n', start)) != -1:
            fmt.append(DraftyFormat(at=p, len=1, tp="BR"))
            start = p + 1
        return DraftyMessage(txt=self.text.replace('\n', ' '), fmt=fmt)
    
    def __str__(self) -> str:
        return self.text


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


class Button(BaseText):
    name: Optional[str] = None
    value: Optional[str] = None
    act: Literal["pub", "url", "note"] = "pub"
    ref: Optional[str] = None

    def to_drafty(self) -> DraftyMessage:
        return super().to_drafty()
    
    def __str__(self) -> str:
        if self.name is None:
            return "<button>"
        if self.value:
            return f"<button {self.name}:{self.value}>"
        return f"<button {self.name}>"


class _AttachmentMessage(BaseText):
    type: ClassVar[Literal["IM", "AU", "VD"]]

    mime: str
    name: Optional[str] = None
    path: Optional[Path] = None
    ref: Optional[str] = None

    def get_val(self) -> str:
        if self.path is None:
            raise ValueError("missing resource path")
        with open(self.path, 'rb') as f:
            return encodebytes(f.read()).decode()
    
    def get_data(self) -> Dict[str, Any]:
        data = self.dict(exclude={"path", "ref"}, exclude_none=True)
        if self.ref:
            data["ref"] = self.ref
        else:
            data["value"] = self.get_val()
        return data

    def to_drafty(self) -> DraftyMessage:
        return DraftyMessage(
            txt=" ",
            fmt=[DraftyFormat(at=0, len=1)],
            ent=[DraftyExtend(
                tp=self.type,
                data=self.get_data()
            )]
        )


class Image(_AttachmentMessage):
    type = "IM"

    mime: str = "image/png"
    width: int
    height: int
    size: Optional[int] = None

    def __str__(self) -> str:
        if self.path:
            return f"<image at {self.path}>"
        return f"<image from {self.ref}>"
