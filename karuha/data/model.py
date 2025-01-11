import base64
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Dict, Mapping, Optional, Type, TypeVar
from typing_extensions import Annotated

from pydantic.annotated_handlers import GetCoreSchemaHandler
from pydantic_core import core_schema, to_json
from pydantic import BaseModel, model_validator, model_serializer


T = TypeVar("T")


if TYPE_CHECKING:
    # Json[list[str]] will be recognized by type checkers as list[str]
    JsonSerialize = Annotated[T, ...]
else:
    class JsonSerialize:
        """A special type wrapper which is used to serialize a type to JSON.

        You can use it to convert a type to JSON bytes in the model serialization.
        """
        @classmethod
        def __class_getitem__(cls, item: Type[T]) -> Type[T]:
            return Annotated[item, cls()]  # type: ignore

        @classmethod
        def __get_pydantic_core_schema__(cls, source: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
            ser = core_schema.plain_serializer_function_ser_schema(
                lambda v: base64.encodebytes(to_json(v)),
                is_field_serializer=False,
                info_arg=False
            )
            if cls is source:
                return core_schema.any_schema(serialization=ser)
            schema = handler(source)
            schema["serialization"] = ser
            return schema
        
        def __repr__(self) -> str:
            return 'JsonSerialize'

        def __hash__(self) -> int:
            return hash(type(self))

        def __eq__(self, other: Any) -> bool:
            return type(other) is type(self)


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

    @model_validator(mode="before")
    def validate_permission(cls, value: Any) -> Any:
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

    @model_serializer(mode="plain")
    def serialize_permission(self) -> str:
        result = ""
        if self.join:
            result += "J"
        if self.read:
            result += "R"
        if self.write:
            result += "W"
        if self.presence:
            result += "P"
        if self.approve:
            result += "A"
        if self.sharing:
            result += "S"
        if self.delete:
            result += "D"
        if self.owner:
            result += "O"
        if not result:
            return "N"
        return result


class Cred(BaseModel):
    method: str
    value: str
    done: bool = False


class DefaultAccess(BaseModel):
    auth: AccessPermission
    anon: AccessPermission


class Access(BaseModel):
    want: AccessPermission
    given: AccessPermission


class ClientDesc(BaseModel):
    default_acs: Optional[DefaultAccess] = None
    public: JsonSerialize[Optional[Dict[str, Any]]] = None
    trusted: JsonSerialize[Optional[Dict[str, Any]]] = None
    private: JsonSerialize[Optional[Dict[str, Any]]] = None


class ClientCred(BaseModel):
    method: str
    value: str
    response: Optional[str] = None
    params: Optional[Mapping[str, bytes]] = None


class BaseInfo(BaseModel, frozen=True):
    public: Optional[Dict[str, Any]] = None
    trusted: Optional[Dict[str, Any]] = None
    private: Optional[Dict[str, Any]] = None

    @property
    @abstractmethod
    def id(self) -> str:
        raise NotImplementedError

    @property
    def fn(self) -> Optional[str]:
        if self.public:
            return self.public.get("fn")

    @property
    def note(self) -> Optional[str]:
        if self.public:
            return self.public.get("note")

    @property
    def comment(self) -> Optional[str]:
        if self.private:
            return self.private.get("comment")

    @property
    def verified(self) -> bool:
        return False if self.trusted is None else self.trusted.get("verified", False)

    @property
    def staff(self) -> bool:
        if self.trusted is None:
            return False
        return self.trusted.get("staff", False)
