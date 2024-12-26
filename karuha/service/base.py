from inspect import Parameter
from typing import Any, Union

from ..bot import Bot
from ..event.bot import BotEvent
from ..text import Message
from ..utils.invoker import HandlerInvokerDependency, KaruhaHandlerInvokerError


class BaseService(HandlerInvokerDependency):
    """
    Base class for all services.
    """
    __slots__ = ["bot"]

    def __init__(self, bot: Bot, /) -> None:
        self.bot = bot
    
    @classmethod
    def resolve_dependency(cls, invoker: Union[Message, BotEvent], param: Parameter, **kwds: Any) -> Any:
        if not hasattr(invoker, "bot"):
            raise KaruhaHandlerInvokerError(f"cannot resolve dependency for {param.name!r}")
        return cls(invoker.bot)
