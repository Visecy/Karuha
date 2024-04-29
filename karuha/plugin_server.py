from concurrent import futures

import grpc
from tinode_grpc import pb, pbx

from .logger import logger
from .event.plugin import TopicEvent, AccountEvent, SubscriptionEvent


class Plugin(pbx.PluginServicer):
    def Topic(self, tpc_event: pb.TopicEvent, context: grpc.ServicerContext):
        logger.debug(f"plugin in: {tpc_event}")
        TopicEvent(tpc_event).trigger()
        return pb.Unused()
    
    def Account(self, acc_event: pb.AccountEvent, context: grpc.ServicerContext):
        logger.debug(f"plugin in: {acc_event}")
        AccountEvent(acc_event).trigger()
        return pb.Unused()
    
    def Subscription(self, sub_event: pb.SubscriptionEvent, context: grpc.ServicerContext):
        logger.debug(f"plugin in: {sub_event}")
        SubscriptionEvent(sub_event).trigger()
        return pb.Unused()


def init_server(address: str) -> grpc.Server:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    pbx.add_PluginServicer_to_server(Plugin(), server)
    server.add_insecure_port(address)
    logger.info(f"plugin server starts at {address}")
    return server
