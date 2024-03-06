from typing import Any, Dict, Mapping, Union

from google.protobuf.internal import containers
from google.protobuf.message import Message

try:
    import ujson as json
except ImportError:  # pragma: no cover
    import json


def load_json(obj: Union[str, bytes], **kwds: Any) -> Any:
    if not obj:
        return
    return json.loads(obj, **kwds)


def encode_mapping(data: Mapping[str, Any]) -> Dict[str, bytes]:
    return {k: json.dumps(v).encode() for k, v in data.items()}


def decode_mapping(data: Mapping[str, bytes]) -> Dict[str, Any]:
    return {k: json.loads(v) for k, v in data.items()}


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
