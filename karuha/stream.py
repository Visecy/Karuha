from typing import Optional

import grpc
from grpc import aio as grpc_aio
from tinode_grpc import pb


def get_channel(host: str, secure: bool = False, ssl_host: Optional[str] = None) -> grpc_aio.Channel:
    if not secure:
        return grpc_aio.insecure_channel(host)
    opts = (('grpc.ssl_target_name_override', ssl_host),)
    return grpc_aio.secure_channel(host, grpc.ssl_channel_credentials(), opts)


def get_stream(channel: grpc_aio.Channel) -> grpc_aio.StreamStreamMultiCallable:
    return channel.stream_stream(
        '/pbx.Node/MessageLoop',
        request_serializer=pb.ClientMsg.SerializeToString,
        response_deserializer=pb.ServerMsg.FromString
    )
