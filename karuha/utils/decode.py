from typing import Any, Dict, Mapping, Union

from google.protobuf.message import Message
from google.protobuf.json_format import MessageToDict
from pydantic_core import from_json, to_json


def load_json(obj: Union[str, bytes], **kwds: Any) -> Any:
    if not obj:
        return
    return from_json(obj, **kwds)


def encode_mapping(data: Mapping[str, Any]) -> Dict[str, bytes]:
    return {k: to_json(v) for k, v in data.items()}


def decode_mapping(data: Mapping[str, bytes]) -> Dict[str, Any]:
    return {k: from_json(v) for k, v in data.items() if v}


def msg2dict(msg: Message) -> Dict[str, Any]:
    return MessageToDict(msg)
