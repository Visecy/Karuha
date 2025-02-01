from datetime import datetime
from typing import Any, Dict, Optional, Union
from typing_extensions import Self

from pydantic import BaseModel, Json
from tinode_grpc import pb

from ..utils.decode import msg2dict
from .model import Access, DefaultAccess


class TimeInfo(BaseModel):
    created: datetime
    updated: datetime
    touched: Optional[datetime] = None


class TopicInfo(TimeInfo):
    seq: Optional[int] = None

    @classmethod
    def from_meta(cls, desc: pb.TopicDesc) -> Self:
        return cls(
            seq=desc.seq_id,
            created=desc.created_at,  # type: ignore
            updated=desc.updated_at,  # type: ignore
            touched=desc.touched_at,  # type: ignore
        )


class BaseDesc(BaseModel):
    public: Optional[Json[Dict[str, Any]]] = None
    trusted: Optional[Json[Dict[str, Any]]] = None

    @classmethod
    def from_meta(cls, meta: Union[pb.TopicDesc, pb.TopicSub]) -> Self:
        return cls(
            public=meta.public or None,  # type: ignore
            trusted=meta.trusted or None,  # type: ignore
        )


class CommonDesc(BaseDesc):
    defacs: Optional[DefaultAccess] = None

    @classmethod
    def from_meta(cls, meta: Union[pb.TopicDesc, pb.TopicSub]) -> Self:
        return cls(
            public=meta.public or None,  # type: ignore
            trusted=meta.trusted or None,  # type: ignore
            defacs=msg2dict(meta.defacs) or None,  # type: ignore
        )


class P2PTopicDesc(TopicInfo):
    @classmethod
    def from_meta(cls, desc: pb.TopicDesc) -> Self:
        return cls(
            seq=desc.seq_id,
            created=desc.created_at,  # type: ignore
            updated=desc.updated_at,  # type: ignore
            touched=desc.touched_at,  # type: ignore
        )


class GroupTopicDesc(TopicInfo, CommonDesc):
    is_chan: bool = False

    @classmethod
    def from_meta(cls, desc: pb.TopicDesc) -> Self:
        return cls(
            public=desc.public or None,  # type: ignore
            trusted=desc.trusted or None,  # type: ignore
            defacs=msg2dict(desc.defacs) or None,  # type: ignore
            seq=desc.seq_id,
            created=desc.created_at,  # type: ignore
            updated=desc.updated_at,  # type: ignore
            touched=desc.touched_at,  # type: ignore
            is_chan=desc.is_chan,
        )


class UserDesc(TimeInfo, CommonDesc):
    state: Optional[str] = None
    state_at: Optional[datetime] = None

    @classmethod
    def from_meta(cls, desc: pb.TopicDesc) -> Self:
        return cls(
            public=desc.public or None,  # type: ignore
            trusted=desc.trusted or None,  # type: ignore
            state=desc.state,
            state_at=desc.state_at,  # type: ignore
            created=desc.created_at,  # type: ignore
            updated=desc.updated_at,  # type: ignore
            touched=desc.touched_at,  # type: ignore
            defacs=msg2dict(desc.defacs) or None,  # type: ignore
        )


class BaseSubscription(BaseModel):
    acs: Access
    private: Optional[Json[Dict[str, Any]]] = None
    read: Optional[int] = None
    recv: Optional[int] = None
    clear: Optional[int] = None

    @classmethod
    def from_meta(cls, meta: Union[pb.TopicDesc, pb.TopicSub]) -> Self:
        return cls(
            acs=msg2dict(meta.acs) or None,  # type: ignore
            private=meta.private or None,  # type: ignore
            read=meta.read_id,
            recv=meta.recv_id,
            clear=meta.del_id,
        )


class Subscription(BaseSubscription):
    updated: datetime
    deleted: Optional[datetime] = None
    touched: Optional[datetime] = None

    @classmethod
    def from_meta(cls, meta: pb.TopicSub) -> Self:
        return cls(
            acs=msg2dict(meta.acs) or None,  # type: ignore
            private=meta.private or None,  # type: ignore
            updated=meta.updated_at,  # type: ignore
            deleted=meta.deleted_at,  # type: ignore
            touched=meta.touched_at,  # type: ignore
            read=meta.read_id,
            recv=meta.recv_id,
            clear=meta.del_id,
        )
