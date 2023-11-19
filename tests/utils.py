from abc import ABC
from typing import cast

from karuha import logger
from karuha.bot import Bot


class BotLike(ABC):
    logger = logger


botlike = cast(Bot, BotLike)
