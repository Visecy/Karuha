from typing import Any, Dict, Literal, Union

from tinode_grpc import pb

from .model import ClientCred, ClientDesc


UserStateType = Literal["ok", "susp", "del", "undef"]
ClientDescType = Union[Dict[str, Any], ClientDesc, pb.SetDesc]
ClientCredType = Union[Dict[str, Any], ClientCred, pb.ClientCred]
