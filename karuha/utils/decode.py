import base64
from typing import Any, Dict, Iterable, Mapping, Type, TypeVar, Union, cast

from google.protobuf.descriptor import Descriptor, FieldDescriptor
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


def _is_map_entry(desc: Descriptor) -> bool:
    if not desc.has_options or not desc.GetOptions().map_entry:
        return False
    key_field: FieldDescriptor = desc.fields_by_name["key"]
    value_field: FieldDescriptor = desc.fields_by_name["value"]

    # check if the type of the key and value fields
    return key_field.type == FieldDescriptor.TYPE_STRING and value_field.type == FieldDescriptor.TYPE_BYTES


def _encode_params(data: Dict[str, Any], desc: Descriptor) -> Dict[str, Any]:
    for field in desc.fields:
        field: FieldDescriptor
        if field.name not in data or field.type != FieldDescriptor.TYPE_MESSAGE:
            continue

        if _is_map_entry(field.message_type) and isinstance(data[field.name], dict):
            data[field.name] = {
                key: value if isinstance(value, bytes) else base64.b64encode(to_json(value))
                for key, value in data[field.name].items()
            }
        elif field.label == FieldDescriptor.LABEL_REPEATED and isinstance(data[field.name], Iterable):
            data[field.name] = [
                _encode_params(item, field.message_type) for item in data[field.name] if isinstance(item, dict)
            ]
        elif isinstance(data[field.name], dict):
            # Handle non-repeated messages.
            data[field.name] = _encode_params(data[field.name], field.message_type)
    return data


def dict2msg(data: Union[BaseModel, Mapping[str, Any], T_Msg], msg: Type[T_Msg], **kwds: Any) -> T_Msg:
    if isinstance(data, msg):
        return data
    if isinstance(data, BaseModel):
        data = data.model_dump(exclude_none=True)
    else:
        data = dict(cast(Mapping[str, Any], data))

    msg_ins = msg()
    data = _encode_params(data, msg_ins.DESCRIPTOR)
    return ParseDict(data, msg_ins, **kwds)


def msg2dict(msg: Message) -> Dict[str, Any]:
    return MessageToDict(msg)
