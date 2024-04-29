from collections import defaultdict

from ..event import on
from ..event.bot import BotFinishEvent, SubscribeEvent, LeaveEvent
from ..bot import Bot


_subscriptions = defaultdict(set)


def _sub_topic(bot: Bot, topic: str) -> None:
    _subscriptions[bot.uid].add(topic)


def _leave_topic(bot: Bot, topic: str) -> None:
    _subscriptions[bot.uid].discard(topic)


def has_sub(bot: Bot, topic: str) -> bool:
    if topic == bot.uid:
        topic = "me"
    return topic in _subscriptions[bot.uid]


async def ensure_sub(bot: Bot, topic: str) -> bool:
    if not has_sub(bot, topic):
        await bot.subscribe(topic=topic, get="desc sub")
        return True
    return False


def reset_sub(bot: Bot) -> None:
    _subscriptions[bot.uid].clear()


@on(SubscribeEvent)
def handle_sub(event: SubscribeEvent) -> None:
    if event.extra is not None and event.extra.on_behalf_of:
        return
    _sub_topic(event.bot, event.topic)


@on(LeaveEvent)
def handle_leave(event: LeaveEvent) -> None:
    if event.extra is not None and event.extra.on_behalf_of:
        return
    _leave_topic(event.bot, event.topic)


@on(BotFinishEvent)
def handle_bot_stop(event: BotFinishEvent) -> None:
    reset_sub(event.bot)
