import asyncio
import os
import re
from typing import Any, Dict, List, NoReturn, Optional, Union, overload
from tinode_grpc import pb
from typing_extensions import Self

import karuha
from .bot import Bot
from .exception import KaruhaRuntimeError


class BaseSession(object):
    __slots__ = ["bot", "topic", "_closed"]

    def __init__(self, /, bot: Bot, topic: str) -> None:
        self.bot = bot
        self.topic = topic
        self._closed = False

    async def send(
            self,
            text: Union[str, dict, "Drafty", "BaseText"],
            /, *,
            head: Optional[Dict[str, Any]] = None,
            timeout: Optional[float] = None,
            topic: Optional[str] = None
    ) -> Optional[int]:
        topic = topic or self.topic
        await self.subscribe(topic)
        if isinstance(text, str) and '\n' in text:
            text = PlainText(text)
        if isinstance(text, BaseText):
            text = text.to_drafty()
        if isinstance(text, Drafty):
            text = text.model_dump(exclude_defaults=True)
            head = head or {}
            head["mime"] = "text/x-drafty"
        _, params = await asyncio.wait_for(
            self.bot.publish(topic, text, head=head),
            timeout
        )
        return params.get("seq")

    send_text = send

    async def send_file(
            self,
            path: Union[str, os.PathLike],
            /, *,
            name: Optional[str] = None,
            mime: Optional[str] = None,
            **kwds: Any
    ) -> Optional[int]:
        return await self.send(
            await File.from_file(
                path, name=name, mime=mime
            ),
            **kwds
        )

    async def send_image(
            self,
            path: Union[str, os.PathLike],
            /, *,
            name: Optional[str] = None,
            mime: Optional[str] = None,
            **kwds: Any
    ) -> Optional[int]:
        return await self.send(
            await Image.from_file(
                path, name=name, mime=mime
            ),
            **kwds
        )

    async def wait_reply(
            self,
            topic: Optional[str] = None,
            user_id: Optional[str] = None,
            pattern: Optional[re.Pattern] = None,
            priority: float = 1.2
    ) -> "Message":
        self._ensure_status()
        loop = asyncio.get_running_loop()
        dispatcher = SessionDispatcher(
            self,
            loop.create_future(),
            topic=topic,
            user_id=user_id,
            pattern=pattern,
            priority=priority
        )
        return await dispatcher.wait()

    async def send_form(
        self,
        title: Union[str, "BaseText"],
        *button: Union[str, "Button"],
        topic: Optional[str] = None,
        **kwds: Any,
    ) -> int:
        chain = TextChain(
            Bold(content=PlainText(title)) if isinstance(title, str) else title
        )
        pred_resp = []
        for i in button:
            if isinstance(i, str):
                name = i.strip().lower()
                i = Button(text=i, name=name)
                pred_resp.append({name: 1})
            elif i.name is not None:
                pred_resp.append({i.name: 1 if i.val is None else i.val})
            else:
                pred_resp.append(None)
            chain += TextChain(NewLine, i)

        async with get_message_lock():
            # Obtain the message lock to ensure that the returned message is intercepted by the dispatcher
            seq_id = await self.send(Form(content=chain), topic=topic, **kwds)
            if not button:
                return 0
            elif seq_id is None:
                raise KaruhaRuntimeError("failed to fetch message id")

            loop = asyncio.get_running_loop()
            dispatcher = ButtonReplyDispatcher(
                self,
                loop.create_future(),
                seq_id=seq_id,
                topic=topic
            )
            dispatcher.activate()
        try:
            resp = await dispatcher.wait()
        except:  # noqa: E722
            # The dispatcher will automatically deactivate after receiving a message,
            # so you only need to actively deactivate it when an exception occurs
            dispatcher.deactivate()
            raise
        return pred_resp.index(resp)

    async def confirm(self, title: Union[str, "BaseText"], **kwds: Any) -> bool:
        return not await self.send_form(title, "Yes", "No", **kwds)

    async def finish(self, text: Union[str, dict, "Drafty", "BaseText"], /, **kwds: Any) -> NoReturn:
        await self.send(text, **kwds)
        self.cancel()

    async def subscribe(
        self,
        topic: Optional[str] = None,
        *,
        force: bool = False,
        get: Union[pb.GetQuery, str, None] = "desc sub",
        **kwds: Any
    ) -> None:
        self._ensure_status()
        topic = topic or self.topic
        if karuha.data.has_sub(self.bot, topic) and not force:
            return
        await self.bot.subscribe(topic, get=get, **kwds)

    async def leave(self, topic: Optional[str] = None, **kwds: Any) -> None:
        self._ensure_status()
        topic = topic or self.topic
        if karuha.data.has_sub(self.bot, topic):
            await self.bot.leave(topic, **kwds)

    @overload
    async def get_data(
        self,
        topic: Optional[str] = None,
        *,
        seq_id: int,
    ) -> "Message": ...

    @overload
    async def get_data(
        self,
        topic: Optional[str] = None,
        *,
        low: Optional[int] = None,
        hi: Optional[int] = None,
    ) -> List["Message"]: ...

    @overload
    async def get_data(
        self,
        topic: Optional[str] = None,
        *,
        seq_id: Optional[int] = None,
        low: Optional[int] = None,
        hi: Optional[int] = None,
    ) -> Union["Message", List["Message"]]: ...

    async def get_data(
        self,
        topic: Optional[str] = None,
        *,
        seq_id: Optional[int] = None,
        low: Optional[int] = None,
        hi: Optional[int] = None,
    ) -> Union["Message", List["Message"]]:
        topic = topic or self.topic
        await self.subscribe(topic)
        return await karuha.data.get_data(
            self.bot, topic, seq_id=seq_id, low=low, hi=hi
        )

    def close(self) -> None:
        self._closed = True

    def cancel(self) -> NoReturn:
        self.close()
        raise asyncio.CancelledError

    def _ensure_status(self) -> None:
        if self._closed:
            raise KaruhaRuntimeError("session is closed")

    @property
    def closed(self) -> bool:
        return self._closed

    async def __aenter__(self) -> Self:
        await self.subscribe()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


from .text.drafty import Drafty
from .text.textchain import (BaseText, Bold, Button, File, Form, Image,
                             NewLine, PlainText, TextChain)
from .text.message import Message
from .utils.dispatcher import FutureDispatcher
from .event.message import MessageDispatcher, get_message_lock


class SessionDispatcher(MessageDispatcher, FutureDispatcher[Message]):
    __slots__ = ["session", "priority", "topic", "user_id", "pattern"]

    def __init__(
            self,
            session: BaseSession,
            /,
            future: asyncio.Future,
            *,
            priority: float = 1.0,
            topic: Optional[str] = None,
            user_id: Optional[str] = None,
            pattern: Optional[re.Pattern] = None
    ) -> None:
        super().__init__(future=future)
        self.session = session
        self.priority = priority
        self.topic = topic or session.topic
        self.user_id = user_id
        self.pattern = pattern
    
    def match(self, message: Message, /) -> float:
        if message.topic != self.topic:
            return -1
        elif self.user_id and message.user_id != self.user_id:
            return -1
        elif self.pattern and not self.pattern.match(message.text):
            return -1
        else:
            return self.priority


class ButtonReplyDispatcher(SessionDispatcher):
    __slots__ = ["seq_id", "_cache"]
    
    def __init__(
            self,
            session: BaseSession,
            /,
            future: asyncio.Future,
            *,
            seq_id: int,
            priority: float = 2.5,
            user_id: Optional[str] = None,
            topic: Optional[str] = None
    ) -> None:
        super().__init__(session, future, priority=priority, user_id=user_id, topic=topic)
        self.seq_id = seq_id
        self._cache = {}
        
    def match(self, message: Message) -> float:
        if super().match(message) < 0:
            return -1
        text = message.raw_text
        if not isinstance(text, Drafty):
            return -1
        for i in text.ent:
            if i.tp != "EX" or i.data.get("mime") != "application/json":
                continue
            value = i.data.get("val")
            if value is None:
                continue
            resp = value.get("resp")
            if value.get("seq") == self.seq_id:
                self._cache[id(message)] = resp
                return self.priority
        return -1
    
    def run(self, message: Message) -> None:
        resp = self._cache.get((id(message)))
        self.future.set_result(resp)
