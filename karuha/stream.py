from typing import Optional

import grpc
from grpc import aio as grpc_aio
from tinode_grpc import pb

from .logger import logger


def get_channel(host: str, secure: bool = False, ssl_host: Optional[str] = None) -> grpc_aio.Channel:
    if not secure:
        logger.info(f"connecting to server at {host}")
        return grpc_aio.insecure_channel(host)
    opts = (('grpc.ssl_target_name_override', ssl_host),) if ssl_host else None
    logger.info(f"connecting to secure server at {host} SNI={ssl_host or host}")
    return grpc_aio.secure_channel(host, grpc.ssl_channel_credentials(), opts)


def get_stream(channel: grpc_aio.Channel) -> grpc_aio.StreamStreamMultiCallable:
    return channel.stream_stream(
        '/pbx.Node/MessageLoop',
        request_serializer=pb.ClientMsg.SerializeToString,
        response_deserializer=pb.ServerMsg.FromString
    )
