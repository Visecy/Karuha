from tinode_grpc import pb

from .bot import DataEvent, CtrlEvent, PresEvent, PublishEvent, LoginEvent
from .message import MessageEvent, MessageDispatcher, get_message_lock


def ensure_text_len(text: str, length: int = 128) -> str:
    if len(text) < length:
        return text
    tail_length = length // 4
    return f"{text[:length-tail_length]} ... {text[-tail_length:]}"


@DataEvent.add_handler
async def _(event: DataEvent) -> None:
    event.bot.logger.info(f"({event.topic})=> {ensure_text_len(event.text)}")
    MessageEvent.from_data_event(event).trigger()
    await event.bot.note_read(event.topic, event.seq_id)


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
    event.bot.logger.info(f"({event.topic})<= {ensure_text_len(event.text)}")


@MessageEvent.add_handler
async def _(event: MessageEvent) -> None:
    async with get_message_lock():
        MessageDispatcher.dispatch(event.dump())
