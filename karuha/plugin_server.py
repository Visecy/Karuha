from concurrent import futures

import grpc
from tinode_grpc import pb, pbx

from .event import Event


class Plugin(pbx.PluginServicer):
    def Account(self, acc_event: pb.AccountEvent, context):
        ...


def init_server(address: str) -> grpc.Server:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    pbx.add_PluginServicer_to_server(server, Plugin())
    return server
