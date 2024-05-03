from abc import ABC, abstractmethod
from typing import Iterable, List, Optional, Tuple, Union

from ..text import BaseText, Message, Quote


class AbstractCommandParser(ABC):
    __slots__ = []

    @abstractmethod
    def parse(self, message: Message) -> Optional[Tuple[str, List[Union[str, BaseText]]]]:
        raise NotImplementedError
    
    def precheck(self, message: Message) -> bool:  # pragma: no cover
        return True

    def check_name(self, name: str) -> bool:  # pragma: no cover
        return True


class SimpleCommandParser(AbstractCommandParser):
    __slots__ = ["prefixs"]

    def __init__(self, prefix: Iterable[str]) -> None:
        self.prefixs = tuple(prefix)
    
    def parse(self, message: Message) -> Optional[Tuple[str, Union[List[str], List[BaseText]]]]:
        text = message.text
        text = text.split()
        if text and isinstance(text[0], Quote):
            text = text[1:]
        if not text:
            return
        
        name = str(text[0])
        for prefix in self.prefixs:
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        else:
            return
        return name, text[1:]
    
    def precheck(self, message: Message) -> bool:
        for prefix in self.prefixs:
            if message.plain_text.startswith(prefix):
                return True
        return False
    
    def check_name(self, name: str) -> bool:
        return ' ' not in name
