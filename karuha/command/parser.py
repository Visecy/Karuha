from abc import ABC, abstractmethod
from typing import Iterable, List, Optional, Tuple, Union

from ..text import BaseText, Message, Mention, Quote


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
        text = message.text.split()
        for i, t in enumerate(text):
            if isinstance(t, (Mention, Quote)):
                continue
            name = str(t).strip()
            if not name:
                continue
            break
        else:
            return
        
        for prefix in self.prefixs:
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        else:
            return
        return name, text[i+1:]
    
    def precheck(self, message: Message) -> bool:
        text = message.text.split()
        for t in text:
            if isinstance(t, (Mention, Quote)):
                continue
            name = str(t).strip()
            return any(name.startswith(prefix) for prefix in self.prefixs)
        return False
    
    def check_name(self, name: str) -> bool:
        return ' ' not in name
