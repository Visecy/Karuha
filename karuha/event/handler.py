from ..text import BaseText
from .bot import *


@DataEvent.add_handler
async def _(event: DataEvent) -> None:
    msg = event.server_message
    event.bot.logger.info(f"({msg.topic})=> {msg.content.decode()}")
    await event.bot.note_read(msg.topic, msg.seq_id)


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
    if msg.what in [pb.ServerPres.ON, pb.ServerPres.MSG]:
        SubscribeEvent(event.bot, msg.src).trigger()
    elif msg.what == pb.ServerPres.OFF:
        LeaveEvent(event.bot, msg.src).trigger()


@PublishEvent.add_handler
async def _(event: PublishEvent) -> None:
    text = event.text
    if isinstance(text, str):
        await event.bot.publish(event.topic, text)
    else:
        if isinstance(text, BaseText):
            text = text.to_drafty()
        await event.bot.publish(
            event.topic,
            text.model_dump(exclude_defaults=True),
            head={"auto": True, "mime": "text/x-drafty"}
        )


@SubscribeEvent.add_handler
async def _(evnet: SubscribeEvent) -> None:
    await evnet.bot.subscribe(evnet.topic)


@LeaveEvent.add_handler
async def _(event: LeaveEvent) -> None:
    await event.bot.leave(event.topic)
