import asyncio
import mimetypes
import os
import re
import weakref
from functools import partialmethod
from io import IOBase
from typing import (Any, BinaryIO, Dict, Iterable, List, NoReturn, Optional,
                    Union, overload)

from aiofiles import open as aio_open
from aiofiles.ospath import getsize
from tinode_grpc import pb
from typing_extensions import Self, deprecated

import karuha

from .bot import Bot
from .exception import KaruhaRuntimeError


class BaseSession(object):
    """Represents a session for interacting with a bot on a specific topic.

    This class manages the communication between the bot and the user,
    allowing for sending messages, handling attachments,
    and managing subscriptions to topics.
    """
    __slots__ = ["bot", "topic", "_task", "_closed"]

    def __init__(self, /, bot: Bot, topic: str) -> None:
        """Initializes the BaseSession with a bot and a topic.

        :param bot: the bot instance to interact with
        :type bot: Bot
        :param topic: the topic to send messages to
        :type topic: str
        """
        self.bot = bot
        self.topic = topic
        self._closed = False
        self._task = None

    def bind_task(self, task: Optional[asyncio.Task] = None) -> Self:
        """Binds an asyncio task to the session.

        :param task: the task to bind; If None, the current task is used, defaults to None
        :type task: Optional[asyncio.Task], optional
        :return: the current session instance
        :rtype: Self
        """
        self._task = task or asyncio.current_task()
        if self._task is not None:
            self._task.add_done_callback(lambda _: self.close())
        return self

    async def send(
            self,
            text: Union[str, dict, "Drafty", "BaseText"],
            /, *,
            head: Optional[Dict[str, Any]] = None,
            timeout: Optional[float] = None,
            topic: Optional[str] = None,
            replace: Optional[int] = None,
            attachments: Optional[Iterable[str]] = None
    ) -> Optional[int]:
        """Send a message to the specified topic.
        
        :param text: the text or Drafty model to send
        :type text: Union[str, dict, "Drafty", "BaseText"]
        :param head: additional metadata to include in the message, defaults to None
        :type head: Optional[Dict[str, Any]], optional
        :param timeout: the timeout in seconds for sending the message, defaults to None
        :type timeout: Optional[float], optional
        :param topic: the topic to send the message to, defaults to None
        :type topic: Optional[str], optional
        :param replace: the message ID to replace, defaults to None
        :type replace: Optional[int], optional
        :param attachments: the list of attachment URLs to include in the message, defaults to None
        :type attachments: Optional[Iterable[str]], optional
        :return: the message ID if successful, None otherwise
        :rtype: Optional[int]"""
        topic = topic or self.topic
        await self.subscribe(topic)
        if replace is not None:
            head = head or {}
            head["replace"] = f":{replace}"
        if isinstance(text, str) and '\n' in text:
            text = PlainText(text)
        if isinstance(text, BaseText):
            text = text.to_drafty()
        if isinstance(text, Drafty):
            text = text.model_dump(exclude_defaults=True)
            head = head or {}
            head["mime"] = "text/x-drafty"
        _, params = await asyncio.wait_for(
            self.bot.publish(
                topic, text, head=head,
                extra=pb.ClientExtra(attachments=attachments) if attachments else None
            ),
            timeout,
        )
        return params.get("seq")

    send_text = send

    async def send_attachment(
            self,
            path: Union[str, os.PathLike],
            /, *,
            name: Optional[str] = None,
            mime: Optional[str] = None,
            attachment_cls_name: str = "File",
            force_upload: bool = False,
            **kwds: Any
    ) -> Optional[int]:
        """Send an attachment to the specified topic.
        
        :param path: the path to the file to send
        :type path: Union[str, os.PathLike]
        :param name: the name of the file, defaults to None
        :type name: Optional[str], optional
        :param mime: the MIME type of the file, defaults to None
        :type mime: Optional[str], optional
        :param attachment_cls_name: the name of the attachment class to use, defaults to "File"
        :type attachment_cls_name: str, optional
        :param force_upload: force upload even if the file size is below the threshold, defaults to False
        :type force_upload: bool, optional
        :return: the message ID if successful, None otherwise
        :rtype: Optional[int]
        """
        self._ensure_status()
        attachment_cls = getattr(textchain, attachment_cls_name, None)
        if attachment_cls is None:
            raise KaruhaRuntimeError("unknown attachment type name")
        elif not issubclass(attachment_cls, _Attachment):
            raise KaruhaRuntimeError("unknown attachment type")
        size = await getsize(path)
        if force_upload or size < self.bot.config.file_size_threshold:
            return await self.send(
                await attachment_cls.from_file(
                    path, name=name, mime=mime
                ),
                **kwds
            )
        _, upload_params = await self.bot.upload(path)
        url = upload_params["url"]
        mime = mime or mimetypes.guess_type(path)[0]
        return await self.send(
            attachment_cls.from_url(url, name=name, mime=mime),
            attachments=[url],
            **kwds
        )

    send_file = partialmethod(send_attachment, attachment_cls_name="File")
    send_image = partialmethod(send_attachment, attachment_cls_name="Image")
    send_audio = partialmethod(send_attachment, attachment_cls_name="Audio")

    async def download_attachment(self, attachment: "textchain._Attachment", path: Union[str, os.PathLike, BinaryIO]) -> None:
        if attachment.raw_val is not None:
            if isinstance(path, (BinaryIO, IOBase)):
                path.write(attachment.raw_val)
            else:
                async with aio_open(path, "wb") as f:
                    await f.write(attachment.raw_val)
        elif attachment.ref is not None:
            await self.bot.download(attachment.ref, path)
        else:
            raise ValueError("attachment has no data")

    async def wait_reply(
            self,
            topic: Optional[str] = None,
            user_id: Optional[str] = None,
            pattern: Optional[re.Pattern] = None,
            priority: float = 1.2
    ) -> "Message":
        """Wait for a reply from the specified topic.
        
        :param topic: the topic to wait for, defaults to None
        :type topic: Optional[str], optional
        :param user_id: the user ID to wait for, defaults to None
        :type user_id: Optional[str], optional
        :param pattern: the pattern to match, defaults to None
        :type pattern: Optional[re.Pattern], optional
        :param priority: the priorityof the message, defaults to 1.2
        :type priority: float, optional
        :return: the message
        :rtype: "Message"
        """
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
        """Send a form to the specified topic.
        
        :param title: the title of the form
        :type title: Union[str, "BaseText"]
        :param button: the buttons to include in the form
        :type button: Union[str, "Button"], optional
        :param topic: the topic to send the form to, defaults to None
        :type topic: Optional[str], optional
        :return: the message ID if successful, None otherwise
        :rtype: int
        """
        self._ensure_status()
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
            elif seq_id is None:  # pragma: no cover
                raise KaruhaRuntimeError("failed to fetch message id")

            loop = asyncio.get_running_loop()
            dispatcher = _ButtonReplyDispatcher(
                self,
                loop.create_future(),
                seq_id=seq_id,
                topic=topic
            )
            dispatcher.activate()
        try:
            resp = await dispatcher.wait()
        except:  # noqa: E722  # pragma: no cover
            # The dispatcher will automatically deactivate after receiving a message,
            # so we only need to actively deactivate it when an exception occurs
            dispatcher.deactivate()
            raise
        return pred_resp.index(resp)

    async def confirm(self, title: Union[str, "BaseText"], **kwds: Any) -> bool:
        """A convenience method to send a form and wait for a reply.
        
        :param title: the title of the form
        :type title: Union[str, "BaseText"]
        :return: True if the user selects "Yes", False otherwise
        :rtype: bool
        """
        return not await self.send_form(title, "Yes", "No", **kwds)

    async def finish(self, text: Union[str, dict, "Drafty", "BaseText"], /, **kwds: Any) -> NoReturn:
        """Finish the session and send a message to the user.
        
        :param text: the message to send
        :type text: Union[str, dict, "Drafty", "BaseText"]
        :raises KaruhaRuntimeError: if the session is not active
        """
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
        """Subscribe to the specified topic.
        
        :param topic: the topic to subscribe to, defaults to None
        :type topic: Optional[str], optional
        :param force: whether to force the subscription, defaults to False
        :type force: bool, optional
        :param get: the query to use, defaults to "desc sub
        :type get: Union[pb.GetQuery, str, None], optional
        """
        self._ensure_status()
        topic = topic or self.topic
        if karuha.data.has_sub(self.bot, topic) and not force:
            return
        await self.bot.subscribe(topic, get=get, **kwds)

    async def leave(self, topic: Optional[str] = None, *, force: bool = False, **kwds: Any) -> None:
        """Leave the specified topic.
        
        :param topic: the topic to leave, defaults to None
        :type topic: Optional[str], optional
        :param force: whether to force the leave, defaults to False
        :type force: bool, optional
        """
        self._ensure_status()
        topic = topic or self.topic
        if karuha.data.has_sub(self.bot, topic) or force:
            await self.bot.leave(topic, **kwds)

    @deprecated("use `UserService` instead")
    async def get_user(self, user_id: str, *, skip_cache: bool = False) -> "karuha.data.BaseUser":
        """Get the user data from the specified user ID.
        
        :param user_id: the user ID to get the data from
        :type user_id: str
        :param ensure_user: whether to ensure that the user exists, defaults to False
        :type ensure_user: bool, optional
        :return: the user data
        :rtype: "karuha.data.BaseUser"
        """
        self._ensure_status()
        return await karuha.data.get_user(self.bot, user_id, skip_cache=skip_cache)

    async def get_topic(self, topic: Optional[str] = None, *, skip_cache: bool = False) -> "karuha.data.BaseTopic":
        """Get the topic data from the specified topic ID.
        
        :param topic: the topic ID to get the data from, defaults to None
        :type topic: Optional[str], optional
        :param ensure_topic: whether to ensure that the topic exists, defaults to False
        :type ensure_topic: bool, optional
        :return: the topic data
        :rtype: "karuha.data.BaseTopic"
        """
        self._ensure_status()
        return await karuha.data.get_topic(self.bot, topic or self.topic, skip_cache=skip_cache)

    @overload
    async def get_data(
        self,
        topic: Optional[str] = None,
        *,
        seq_id: int,
    ) -> "Message":
        """Get the message data from the specified message ID.
        
        :param topic: the topic ID to get the data from, defaults to None
        :type topic: Optional[str], optional
        :param seq_id: the message ID to get the data from
        :type seq_id: int
        :return: the message data
        :rtype: "Message"
        """

    @overload
    async def get_data(
        self,
        topic: Optional[str] = None,
        *,
        low: Optional[int] = None,
        hi: Optional[int] = None,
    ) -> List["Message"]:
        """Get the message data from the specified range.
        
        :param topic: the topic ID to get the data from, defaults to None
        :type topic: Optional[str], optional
        :param low: the lower bound of the range, defaults to None
        :type low: Optional[int], optional
        :param hi: the upper bound of the range, defaults to None
        :type hi: Optional[int], optional
        :return: the message data
        :rtype: List["Message"]
        """

    @overload
    async def get_data(
        self,
        topic: Optional[str] = None,
        *,
        seq_id: Optional[int] = None,
        low: Optional[int] = None,
        hi: Optional[int] = None,
    ) -> Union["Message", List["Message"]]:
        """Get the message data from the specified range.
        
        :param topic: the topic ID to get the data from, defaults to None
        :type topic: Optional[str], optional
        :param seq_id: the message ID to get the data from, defaults to None
        :type seq_id: Optional[int], optional
        :param low: the lower bound of the range, defaults to None
        :type low: Optional[int], optional
        :param hi: the upper bound of the range, defaults to None
        :type hi: Optional[int], optional
        :return: the message data
        :rtype: Union["Message", List["Message"]]
        """

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
        """Close the session."""
        self._closed = True

    def cancel(self) -> NoReturn:
        """Cancel the session.

        :raises asyncio.CancelledError: cancels the session
        """
        self.close()
        if (
            self._task is not None
            and self._task is not asyncio.current_task()
            and not self._task.done()
        ):
            self._task.cancel()
        raise asyncio.CancelledError

    @property
    def closed(self) -> bool:
        """Whether the session is closed."""
        return self._closed

    async def __aenter__(self) -> Self:
        """Enter the session."""
        self.bind_task()
        await self.subscribe()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the session."""
        self.close()

    def _ensure_status(self) -> None:
        if self._closed:
            raise KaruhaRuntimeError("session is closed")


from .event.message import MessageDispatcher, get_message_lock
from .text import textchain
from .text.drafty import Drafty
from .text.message import Message
from .text.textchain import (BaseText, Bold, Button, Form, NewLine, PlainText,
                             TextChain, _Attachment)
from .utils.dispatcher import FutureDispatcher


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
            return 0
        elif self.user_id and message.user_id != self.user_id:
            return 0
        elif self.pattern and not self.pattern.match(message.text):
            return 0
        else:
            return self.priority


class _ButtonReplyDispatcher(SessionDispatcher):
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
            return 0
        text = message.raw_text
        if not isinstance(text, Drafty):
            return 0
        for i in text.ent:
            if i.tp != "EX" or i.data.get("mime") != "application/json":
                continue
            value = i.data.get("val")
            if value is None:
                continue
            resp = value.get("resp")
            if value.get("seq") == self.seq_id:
                self._cache[id(message)] = resp
                weakref.finalize(message, self._cache.pop, id(message), None)
                return self.priority
        return 0
    
    def run(self, message: Message) -> None:
        resp = self._cache[id(message)]
        self.future.set_result(resp)
