from ..bot import Bot
from ..event import PublishEvent, SubscribeEvent, LeaveEvent


class Session(object):
    def __init__(self, bot: Bot, topic: str, user_id: str):
        self.bot = bot
        self.topic = topic
        self.user_id = user_id

    def publish(self, message, *, bot=None, topic=None) -> None:
        '''Encapsulate the PublishEvent class'''
        PublishEvent.new(bot or self.bot, topic or self.topic, message)

    def subscribe(self, *, bot=None, topic=None) -> None:
        '''Encapsulate the SubscribeEvent class'''
        SubscribeEvent.new(bot or self.bot, topic or self.topic)

    def leave(self, *, bot=None, topic=None):
        '''Encapsulate the SubscribeEvent class'''
        LeaveEvent.new(bot or self.bot, topic or self.topic)
