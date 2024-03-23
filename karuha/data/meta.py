from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from typing_extensions import Self

from pydantic import BaseModel, Json, model_validator
from tinode_grpc import pb

from ..utils.decode import msg2dict


class AccessPermission(BaseModel):
    """
    User's access to a topic is defined by two sets of permissions:
    user's desired permissions "want", and permissions granted to user by topic's manager(s) "given".
    Each permission is represented by a bit in a bitmap.
    It can be either present or absent.
    The actual access is determined as a bitwise AND of wanted and given permissions.
    The permissions are communicated in messages as a set of ASCII characters,
    where presence of a character means a set permission bit:

    - No access: N is not a permission per se but an indicator that permissions are explicitly cleared/not set.
        It usually indicates that the default permissions should not be applied.
    - Join: J, permission to subscribe to a topic
    - Read: R, permission to receive {data} packets
    - Write: W, permission to {pub} to topic
    - Presence: P, permission to receive presence updates {pres}
    - Approve: A, permission to approve requests to join a topic, remove and ban members;
        a user with such permission is topic's administrator
    - Sharing: S, permission to invite other people to join the topic
    - Delete: D, permission to hard-delete messages; only owners can completely delete topics
    - Owner: O, user is the topic owner; the owner can assign any other permission to any topic member,
        change topic description, delete topic; topic may have a single owner only;
        some topics have no owner
    """
    join: bool = False
    read: bool = False
    write: bool = False
    presence: bool = False
    approve: bool = False
    sharing: bool = False
    delete: bool = False
    owner: bool = False

    @model_validator(mode="before")  # type: ignore
    def validate(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        value = value.upper()
        result = {}
        if value == "N":
            return result
        for i in value:
            if i == "J":
                result["join"] = True
            elif i == "R":
                result["read"] = True
            elif i == "W":
                result["write"] = True
            elif i == "P":
                result["presence"] = True
            elif i == "A":
                result["approve"] = True
            elif i == "S":
                result["sharing"] = True
            elif i == "D":
                result["delete"] = True
            elif i == "O":
                result["owner"] = True
            else:
                raise ValueError(f"unknown permission: {i}")
        return result


class Cred(BaseModel):
    method: str
    value: str
    done: bool


class DefaultAccess(BaseModel):
    auth: AccessPermission
    anon: AccessPermission


class Access(BaseModel):
    want: AccessPermission
    given: AccessPermission


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
            public=meta.public,  # type: ignore
            trusted=meta.trusted  # type: ignore
        )


class CommonDesc(BaseDesc):
    defacs: Optional[DefaultAccess] = None


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
            public=desc.public,  # type: ignore
            trusted=desc.trusted,  # type: ignore
            defacs=msg2dict(desc.defacs),  # type: ignore
            seq=desc.seq_id,
            created=desc.created_at,  # type: ignore
            updated=desc.updated_at,  # type: ignore
            touched=desc.touched_at,  # type: ignore
            is_chan=desc.is_chan
        )


class UserDesc(TimeInfo, CommonDesc):
    state: Optional[str] = None
    state_at: Optional[datetime] = None

    @classmethod
    def from_meta(cls, desc: pb.TopicDesc) -> Self:
        return cls(
            public=desc.public,  # type: ignore
            trusted=desc.trusted,  # type: ignore
            state=desc.state,
            state_at=desc.state_at,  # type: ignore
            created=desc.created_at,  # type: ignore
            updated=desc.updated_at,  # type: ignore
            touched=desc.touched_at,  # type: ignore
            defacs=msg2dict(desc.defacs)  # type: ignore
        )


class BaseSubscription(BaseModel):
    acs: Access
    private: Optional[Dict[str, Any]] = None

    @classmethod
    def from_meta(cls, meta: Union[pb.TopicDesc, pb.TopicSub]) -> Self:
        return cls(
            acs=msg2dict(meta.acs),  # type: ignore
            private=meta.private,  # type: ignore
        )


class Subscription(BaseSubscription):
    updated: datetime
    deleted: Optional[datetime] = None
    read: Optional[int] = None
    recv: Optional[int] = None
    clear: Optional[int] = None

    @classmethod
    def from_meta(cls, meta: pb.TopicSub) -> Self:
        return cls(
            acs=msg2dict(meta.acs),  # type: ignore
            private=meta.private,  # type: ignore
            updated=meta.updated_at,  # type: ignore
            deleted=meta.deleted_at,  # type: ignore
            read=meta.read,  # type: ignore
            recv=meta.recv,  # type: ignore
            clear=meta.clear,  # type: ignore
        )


UserTags = List[str]
UserCred = List[Cred]
