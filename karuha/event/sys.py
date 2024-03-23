from typing import Iterable

from .base import Event
from ..bot import Bot
from ..config import Config


class SystemEvent(Event):
    __slots__ = ["config"]

    def __init__(self, config: Config) -> None:
        self.config = config


class SystemStartEvent(SystemEvent):
    __slots__ = ["bots"]

    def __init__(self, config: Config, bots: Iterable["Bot"]) -> None:
        super().__init__(config)
        self.bots = tuple(bots)


class SystemStopEvent(SystemEvent):
    __slots__ = []
