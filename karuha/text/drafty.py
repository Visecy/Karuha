"""
Tinode Drafty Message Support

For details see: https://github.com/tinode/chat/blob/master/docs/drafty.md
"""

from pydantic import BaseModel
from typing import Any, Dict, List, Literal, Optional, Union
from typing_extensions import Self


InlineType = Literal["BR", "CO", "FM", "RW", "HL", "DL", "EM", "ST", "HD"]
ExtendType = Literal["AU", "BN", "EX", "FM", "HT", "IM", "LN", "MN", "RW", "VC", "VD"]


class DraftyFormat(BaseModel, frozen=True):
    at: int = 0     # -1 means not applying any styling to text.
    len: int = 0
    key: int = 0
    tp: Optional[InlineType] = None

    def rebase(self, offset: int, k_base: int = 0) -> Self:
        return self.model_copy(
            update={
                "at": self.at if self.at < 0 else self.at + offset,
                "key": self.key if self.tp is not None else self.key + k_base,
            }
        )


class DraftyExtend(BaseModel, frozen=True):
    tp: ExtendType
    data: Dict[str, Any]


class Drafty(BaseModel):
    txt: str
    fmt: List[DraftyFormat] = []
    ent: List[DraftyExtend] = []

    @classmethod
    def from_str(cls, string: str) -> Self:
        return Drafty(txt=string)

    def __add__(self, other: Union[str, "Drafty"]) -> Self:
        obj = self.model_copy()
        obj += other
        return obj
    
    def __radd__(self, other: str) -> Self:
        if not isinstance(other, str):
            return NotImplemented
        obj = self.model_copy()
        obj.txt = other + obj.txt
        return obj
    
    def __iadd__(self, other: Union[str, "Drafty"]) -> Self:
        if isinstance(other, str):
            self.txt += other
            return self
        elif not isinstance(other, Drafty):
            return NotImplemented
        offset = len(self.txt)
        k_base = len(self.ent)
        self.txt += other.txt

        if not k_base:
            self.ent = other.ent
            self.fmt.extend(i.rebase(offset, 0) for i in other.fmt)
            return self
        repeat = {}
        for i, e in enumerate(other.ent):
            for j, v in enumerate(self.ent):
                if v == e:
                    break
            else:
                self.ent.append(e)
                continue
            repeat[i] = j - i
        self.fmt.extend(
            v.rebase(offset, repeat.get(i, k_base)) for i, v in enumerate(other.fmt)
        )
        return self

    def __repr__(self) -> str:
        return f"<drafty message {self.txt!r}>"
    
    def __str__(self) -> str:
        return self.txt
