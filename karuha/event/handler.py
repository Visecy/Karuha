from tinode_grpc import pb

from .bot import DataEvent, CtrlEvent, PresEvent, PublishEvent, LoginEvent
from .message import MessageEvent, MessageDispatcher


@DataEvent.add_handler
async def _(event: DataEvent) -> None:
    msg = event.server_message
    await event.bot.note_read(msg.topic, msg.seq_id)


@DataEvent.add_handler
async def _(event: DataEvent) -> None:
    MessageEvent.from_data_event(event).trigger()


@CtrlEvent.add_handler
async def _(event: CtrlEvent) -> None:
    tid = event.server_message.id
    if tid in event.bot._wait_list:
        event.bot._wait_list[tid].set_result(event.server_message)


@PresEvent.add_handler
async def _(event: PresEvent) -> None:
    msg = event.server_message
    if msg.topic != "me":
        return
    if msg.what == pb.ServerPres.ON:
        await event.bot.subscribe(msg.src)
    elif msg.what == pb.ServerPres.MSG:
        await event.bot.subscribe(msg.src, get_since=msg.seq_id)
    elif msg.what == pb.ServerPres.OFF:
        await event.bot.leave(msg.src)


@LoginEvent.add_handler
async def _(event: LoginEvent) -> None:
    await event.bot.subscribe("me")


@PublishEvent.add_handler
async def _(event: PublishEvent) -> None:
    event.bot.logger.info(f"({event.topic})<= {event.text}")


@MessageEvent.add_handler
async def _(event: MessageEvent) -> None:
    event.bot.logger.info(f"({event.topic})=> {event.text}")


@MessageEvent.add_handler
async def _(event: MessageEvent) -> None:
    MessageDispatcher.dispatch(event)
