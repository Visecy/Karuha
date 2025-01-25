from concurrent import futures

import grpc
from tinode_grpc import pb, pbx

from .logger import logger
from .event.plugin import TopicEvent, AccountEvent, SubscriptionEvent


class Plugin(pbx.PluginServicer):
    async def Topic(self, tpc_event: pb.TopicEvent, context: grpc.ServicerContext):
        logger.debug(f"plugin in: {tpc_event}")
        await TopicEvent.new_and_wait(tpc_event)
        return pb.Unused()
    
    async def Account(self, acc_event: pb.AccountEvent, context: grpc.ServicerContext):
        logger.debug(f"plugin in: {acc_event}")
        await AccountEvent.new_and_wait(acc_event)
        return pb.Unused()
    
    async def Subscription(self, sub_event: pb.SubscriptionEvent, context: grpc.ServicerContext):
        logger.debug(f"plugin in: {sub_event}")
        await SubscriptionEvent.new_and_wait(sub_event)
        return pb.Unused()


def init_server(address: str) -> grpc.aio.Server:
    server = grpc.aio.server()
    pbx.add_PluginServicer_to_server(Plugin(), server)
    server.add_insecure_port(address)
    logger.info(f"plugin server starts at {address}")
    return server
