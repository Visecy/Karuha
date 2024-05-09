import re
from abc import ABC, abstractmethod
from typing import Any, Optional, Union

from typing_extensions import Self

from ..event.message import MessageDispatcher
from ..text import Message


class BaseRule(ABC):
    """
    Base class for all rules.
    """

    __slots__ = []

    @abstractmethod
    def match(self, message: Message, /) -> float:
        """
        Returns a score between 0 and 1 indicating how well the rule matches the message.
        """
        raise NotImplementedError
    
    def __and__(self, other: "BaseRule") -> "AndRule":
        return AndRule(self, other)
    
    def __or__(self, other: "BaseRule") -> "OrRule":
        return OrRule(self, other)
    
    def __invert__(self) -> "NotRule":
        return NotRule(self)


class BaseSingletonRule(BaseRule):
    """
    A base class for rules that do not require any arguments.
    """

    __slots__ = []

    __rule_instance__: Optional[Self] = None

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        if args or kwargs:  # pragma: no cover
            # back to normal mode
            return super().__new__(cls, *args, **kwargs)
        # singleton mode
        if cls.__rule_instance__ is None or type(cls.__rule_instance__) is not cls:
            cls.__rule_instance__ = super().__new__(cls)
        return cls.__rule_instance__


class AndRule(BaseRule):
    """
    A rule that matches if all of its subrules match.
    """

    __slots__ = ["rules"]

    def __init__(self, *rules: BaseRule) -> None:
        self.rules = rules

    def match(self, message: Message, /) -> float:
        score = 1.0
        for rule in self.rules:
            score *= rule.match(message)
        return score
    
    def __iand__(self, other: BaseRule) -> Self:
        self.rules += (other,)
        return self


class OrRule(BaseRule):
    """
    A rule that matches if any of its subrules match.
    """

    __slots__ = ["rules"]

    def __init__(self, *rules: BaseRule) -> None:
        self.rules = rules

    def match(self, message: Message, /) -> float:
        scores = [0.0]
        for rule in self.rules:
            scores.append(rule.match(message))
        return max(scores)
    
    def __ior__(self, other: BaseRule) -> Self:
        self.rules += (other,)
        return self


class NotRule(BaseRule):
    """
    A rule that matches if its subrule does not match.
    """

    __slots__ = ["rule"]

    def __init__(self, rule: BaseRule) -> None:
        self.rule = rule

    def match(self, message: Message, /) -> float:
        return 1.0 - self.rule.match(message)


class TopicRule(BaseRule):
    """
    A rule that matches if the message's topic matches the given topic.
    """

    __slots__ = ["topic"]

    def __init__(self, topic: str) -> None:
        self.topic = topic

    def match(self, message: Message, /) -> float:
        return 1.0 if message.topic == self.topic else 0.0


class SeqIDRule(BaseRule):
    """
    A rule that matches if the message's seq_id matches the given seq_id.
    """

    __slots__ = ["topic", "seq_id"]

    def __init__(self, topic: str, seq_id: int) -> None:
        self.topic = topic
        self.seq_id = seq_id

    def match(self, message: Message, /) -> float:
        return 1.0 if message.seq_id == self.seq_id and message.topic == self.topic else 0.0


class UserIDRule(BaseRule):
    """
    A rule that matches if the message's user_id matches the given user_id.
    """

    __slots__ = ["user_id"]

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id

    def match(self, message: Message, /) -> float:
        return 1.0 if message.user_id == self.user_id else 0.0


class KeywordRule(BaseRule):
    """
    A rule that matches if the message's text contains the given keyword.
    """

    __slots__ = ["keyword"]

    def __init__(self, keyword: str) -> None:
        self.keyword = keyword

    def match(self, message: Message, /) -> float:
        return 1.0 if self.keyword in message.text else 0.0


class RegexRule(BaseRule):
    """
    A rule that matches if the message's text matches the given regex.
    """

    __slots__ = ["regex"]

    def __init__(self, regex: Union[str, re.Pattern]) -> None:
        self.regex = regex if isinstance(regex, re.Pattern) else re.compile(regex)

    def match(self, message: Message, /) -> float:
        return 1.0 if self.regex.search(message.plain_text) else 0.0


class MentionRule(BaseRule):
    """
    A rule that matches if the message's text contains the given mention.
    """

    __slots__ = ["mention"]

    def __init__(self, mention: str) -> None:
        self.mention = mention

    def match(self, message: Message, /) -> float:
        if isinstance(message.raw_text, str):
            return 0.0
        ent = message.raw_text.ent
        return 1.0 if any(e.tp == "MN" and e.data.get("val") == self.mention for e in ent) else 0.0


class MentionMeRule(BaseSingletonRule):
    """
    A rule that matches if the message's text contains the bot's mention.
    """

    __slots__ = []

    @staticmethod
    def match(message: Message, /) -> float:
        if isinstance(message.raw_text, str):
            return 0.0
        uid = message.bot.user_id
        ent = message.raw_text.ent
        return 1.0 if any(e.tp == "MN" and e.data.get("val") == uid for e in ent) else 0.0


class ToMeRule(BaseSingletonRule):
    """
    A rule that matches if it is in the private chat or the message's text contains the bot's mention.
    """

    __slots__ = []

    @staticmethod
    def match(message: Message, /) -> float:
        if message.topic.startswith("usr"):
            return 1.0
        return MentionMeRule.match(message)


class QuoteRule(BaseRule):
    """
    A rule that matches messages containing a quote.
    """

    __slots__ = ["topic", "mention", "reply"]

    def __init__(self, /, mention: Optional[str] = None, reply: Optional[int] = None) -> None:
        self.mention = mention
        self.reply = reply
    
    def match(self, message: Message, /) -> float:
        if isinstance(message.text, str):
            return 0.0
        elif self.reply is not None:
            try:
                reply_id = int(message.head["reply"])
            except (KeyError, ValueError):
                return 0.0
            if reply_id != self.reply:
                return 0.0
        quote = message.quote
        if quote is None:
            return 0.0
        if self.mention is not None:
            if quote.mention is None or quote.mention.val != self.mention:
                return 0.0
        return 1.0


class NoopRule(BaseSingletonRule):
    """
    A rule that matches all messages.
    """

    __slots__ = []

    @staticmethod
    def match(message: Message, /) -> float:
        return 1.0
    
    def __and__(self, other: BaseRule) -> BaseRule:
        return other


class MessageRuleDispatcher(MessageDispatcher):
    __slots__ = ["rule", "weights"]

    def __init__(self, rule: BaseRule, weights: float = 1.5, *, once: bool = False) -> None:
        super().__init__(once=once)
        self.rule = rule
        self.weights = weights

    def match(self, message: Message, /) -> float:
        return self.rule.match(message) * self.weights


def rule(
    *,
    topic: Optional[str] = None,
    seq_id: Optional[int] = None,
    user_id: Optional[str] = None,
    keyword: Optional[str] = None,
    regex: Optional[Union[str, re.Pattern]] = None,
    mention: Optional[str] = None,
    to_me: bool = False,
    quote: Optional[int] = None,
) -> BaseRule:
    """
    A decorator that creates a rule.
    """
    base = NoopRule()
    if seq_id is not None:
        assert topic is not None, "topic must be specified when seq_id is specified"
        base &= SeqIDRule(topic, seq_id)
    elif topic is not None:
        base &= TopicRule(topic)

    if user_id is not None:
        base &= UserIDRule(user_id)
    if keyword is not None:
        base &= KeywordRule(keyword)
    if regex is not None:
        base &= RegexRule(regex)
    if mention is not None:
        base &= MentionRule(mention)
    if to_me:
        base &= ToMeRule()
    if quote is not None:
        base &= QuoteRule(reply=quote)
    return base
