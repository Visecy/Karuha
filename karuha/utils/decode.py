from typing import Any, Dict, Mapping, Type, TypeVar, Union

from google.protobuf.message import Message
from google.protobuf.json_format import MessageToDict, ParseDict
from pydantic import BaseModel
from pydantic_core import from_json, to_json


def load_json(obj: Union[str, bytes], **kwds: Any) -> Any:
    if not obj:
        return
    return from_json(obj, **kwds)


def encode_mapping(data: Mapping[str, Any]) -> Dict[str, bytes]:
    return {k: to_json(v) for k, v in data.items()}


def decode_mapping(data: Mapping[str, bytes]) -> Dict[str, Any]:
    return {k: from_json(v) for k, v in data.items() if v}


T_Msg = TypeVar("T_Msg", bound=Message)


def dict2msg(data: Union[BaseModel, Mapping[str, Any], T_Msg], msg: Type[T_Msg]) -> T_Msg:
    if isinstance(data, msg):
        return data
    if isinstance(data, BaseModel):
        data = data.model_dump(exclude_none=True)
    return ParseDict(data, msg())


def msg2dict(msg: Message) -> Dict[str, Any]:
    return MessageToDict(msg)
