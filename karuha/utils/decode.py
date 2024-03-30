from typing import Any, Dict, Mapping, Union

from google.protobuf.internal import containers
from google.protobuf.message import Message
from pydantic_core import from_json, to_json


def load_json(obj: Union[str, bytes], **kwds: Any) -> Any:
    if not obj:
        return
    return from_json(obj, **kwds)


def encode_mapping(data: Mapping[str, Any]) -> Dict[str, bytes]:
    return {k: to_json(v) for k, v in data.items()}


def decode_mapping(data: Mapping[str, bytes]) -> Dict[str, Any]:
    return {k: from_json(v) for k, v in data.items()}


def msg2dict(msg: Message) -> Dict[str, Any]:
    return _msg2obj(msg)


def _msg2obj(msg: Any) -> Any:
    if isinstance(msg, Message):
        return {k.name: _msg2obj(v) for k, v in msg.ListFields()}
    elif isinstance(msg, containers.ScalarMap):
        return dict(msg)
    elif isinstance(msg, containers.BaseContainer):
        return list(msg)
    return msg
