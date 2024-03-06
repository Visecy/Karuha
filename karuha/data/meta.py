from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Json, model_validator


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


class SeqInfo(BaseModel):
    read: Optional[int] = None
    recv: Optional[int] = None
    clear: Optional[int] = None


class TopicInfo(TimeInfo, SeqInfo):
    seq: int


class BaseDesc(BaseModel):
    public: Optional[Json[Dict[str, Any]]] = None
    trusted: Optional[Json[Dict[str, Any]]] = None


class CommonDesc(BaseDesc):
    defacs: Optional[DefaultAccess] = None


class P2PTopic(TopicInfo):
    pass


class GroupTopic(TopicInfo, CommonDesc):
    is_chan: bool = False


class User(TimeInfo, CommonDesc):
    state: Optional[str] = None
    state_at: Optional[datetime] = None


class BaseSubscription(BaseModel):
    acs: Access
    private: Optional[Dict[str, Any]] = None


class Subscription(BaseSubscription, SeqInfo):
    updated: datetime
    deleted: datetime


UserTags = List[str]
UserCred = List[Cred]
