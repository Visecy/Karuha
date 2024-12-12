from typing import Literal, TypeVar, Union, Dict, Any

from tinode_grpc import pb
from .model import ClientCred


T = TypeVar("T")


UserStateType = Literal["ok", "susp", "del", "undef"]
ClientCredType = Union[Dict[str, Any], ClientCred, pb.ClientCred]
