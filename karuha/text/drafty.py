"""
Tinode Drafty Message Support

For details see: https://github.com/tinode/chat/blob/master/docs/drafty.md
"""

from pydantic import Field
from typing import Any, Dict, List, Literal, Optional, Tuple, Union
from typing_extensions import Self

from ..config import BaseModel


class DraftyFormat(BaseModel):
    at: int = Field(0, ge=-1)  # -1 means not applying any styling to text.
    len: int = 0
    key: int = 0
    tp: Optional[Literal["BR", "CO", "DL", "EM", "FM", "HD", "HL", "RW", "ST"]] = None

    def rebase(self, offset: int, k_base: int = 0) -> Self:
        obj = self.copy()
        if self.at != -1:
            obj.at += offset
        if obj.tp is None:
            obj.key += k_base
        return obj
    
    def split(self, pos: int) -> Tuple[Self, Self]:
        if pos >= self.len or pos == 0:
            raise ValueError(f"split position {pos} out of range ({self.len})")
        front = self.copy()
        front.len = pos
        back = self.copy()
        back.at += pos
        back.len -= pos
        return front, back
    
    def dict(self, *, exclude_defaults: Literal[True] = True, **kwds) -> Dict:
        return super().dict(exclude_defaults=True, **kwds)


class DraftyExtend(BaseModel):
    tp: Literal["AU", "BN", "EX", "FM", "HT", "IM", "LN", "MN", "RW", "VC", "VD"]
    data: Dict[str, Any]


class DraftyMessage(BaseModel):
    txt: str
    fmt: List[DraftyFormat] = []
    ent: List[DraftyExtend] = []

    def __add__(self, other: Union[str, "DraftyMessage"]) -> Self:
        obj = self.copy()
        if isinstance(other, str):
            obj.txt += other
            return obj
        elif not isinstance(other, DraftyMessage):
            return NotImplemented
        offset = len(obj.txt)
        k_base = len(obj.ent)
        obj.ent.extend(other.ent)
        obj.fmt.extend(i.rebase(offset, k_base) for i in other.fmt)
        return obj
    
    def __radd__(self, other: Union[str, "DraftyMessage"]) -> Self:
        if not isinstance(other, str):
            return NotImplemented
        obj = self.copy()
        obj.txt = other + obj.txt
        return obj
    
    def __iadd__(self, other: Union[str, "DraftyMessage"]) -> Self:
        if isinstance(other, str):
            self.txt += other
            return self
        elif not isinstance(other, DraftyMessage):
            return NotImplemented
        offset = len(self.txt)
        k_base = len(self.ent)
        self.ent.extend(other.ent)
        self.fmt.extend(i.rebase(offset, k_base) for i in other.fmt)
        return self

    def __repr__(self) -> str:
        return f"<drafty message '{self.txt}'>"
    
    def __str__(self) -> str:
        return self.txt
