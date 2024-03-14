from collections import defaultdict

from ..bot import Bot


_subscriptions = defaultdict(set)


def _sub_topic(bot: Bot, topic: str) -> None:
    _subscriptions[bot.uid].add(topic)


def _leave_topic(bot: Bot, topic: str) -> None:
    _subscriptions[bot.uid].discard(topic)


def has_sub(bot: Bot, topic: str) -> bool:
    return topic in _subscriptions[bot.uid]


async def ensure_sub(bot: Bot, topic: str) -> bool:
    if not has_sub(bot, topic):
        await bot.subscribe(topic=topic)
        return True
    return False
