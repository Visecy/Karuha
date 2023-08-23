from typing import Optional
from grpc import RpcError

from . import bot


class KaruhaException(Exception):
    """base exception for all errors in Karuha module"""
    __slots__ = []


class KaruhaConnectError(KaruhaException, RpcError):
    """grpc connection error"""
    __slots__ = []


class KaruhaBotError(KaruhaException):
    """unspecified chatbot run-time error"""
    __slots__ = ["bot"]

    def __init__(self, *args: object, bot: Optional["bot.Bot"] = None) -> None:
        super().__init__(*args)
        self.bot = bot


class KaruhaEventError(KaruhaException):
    """node network system error"""
    __slots__ = []
