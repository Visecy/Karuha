import asyncio
import base64
import os
import platform
import sys
from collections import defaultdict
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from enum import IntEnum
from typing import (Any, AsyncGenerator, BinaryIO, Callable, Coroutine, Dict,
                    Generator, Iterable, List, Literal, Optional, Tuple, Union,
                    overload)
from weakref import WeakSet, ref

from aiofiles import open as aio_open
from google.protobuf.message import Message
from pydantic import GetCoreSchemaHandler, TypeAdapter
from pydantic_core import CoreSchema, core_schema, from_json, to_json
from tinode_grpc import pb
from typing_extensions import Self, deprecated

from .config import Bot as BotConfig
from .config import Config
from .config import Server as ServerConfig
from .config import get_config, init_config
from .logger import Level, get_sub_logger
from .server import BaseServer, get_server_type
from .utils.decode import decode_mapping, encode_mapping
from .version import APP_VERSION, LIB_VERSION
from .exception import KaruhaBotError, KaruhaServerError, KaruhaTimeoutError


class BotState(IntEnum):
    disabled = 0
    running = 1
    stopped = 2
    restarting = 3
    cancelling = 4


class Bot(object):
    """
    the core class of the chatbot

    Provides many low-level API interfaces.
    """
    
    __slots__ = [
        "state", "logger", "config", "server", "server_info", "account_info",
        "_wait_list", "_tid_counter", "_tasks", "_loop_task_ref", "_server_config"
    ]

    initialize_event_callback: Callable[[Self], Any]
    finalize_event_callback: Callable[[Self], Coroutine]
    server_event_callbacks: Dict[
        str,
        List[
            Callable[[Self, Message], Any]
        ]
    ] = defaultdict(list)
    client_event_callbacks: Dict[
        str,
        List[
            Callable[[Self, Message, Optional[Message], Optional[pb.ClientExtra]], Any]
        ],
    ] = defaultdict(list)

    @overload
    def __init__(
        self,
        config: BotConfig,
        /, *,
        server: Union[ServerConfig, Any, None] = None,
        log_level: Level = ...
    ) -> None:
        """
        :param config: the bot configuration
        :type config: :class:`BotConfig`
        :param server: the server configuration
        :type server: Union[:class:`ServerConfig`, Any, None]
        :param log_level: the log level
        :type log_level: Union[str, int]
        :raises ValueError: if the authentication scheme is not defined
        """

    @overload
    def __init__(
        self, name: str, /,
        scheme: Literal["basic", "token", "cookie"],
        secret: str,
        *,
        server: Union[ServerConfig, Any, None] = None,
        log_level: Level = ...
    ) -> None:
        """
        :param name: the bot name
        :type name: str
        :param scheme: the authentication scheme
        :type scheme: Literal["basic", "token", "cookie"]
        :param secret: the authentication secret
        :type secret: str
        :param server: the server configuration
        :type server: Union[:class:`ServerConfig`, Any, None]
        :param log_level: the log level
        """

    def __init__(
        self,
        name: Union[str, BotConfig],
        /,
        scheme: Optional[Literal["basic", "token", "cookie"]] = None,
        secret: Optional[str] = None,
        *,
        server: Union[ServerConfig, Any, None] = None,
        log_level: Optional[Level] = None
    ) -> None:
        if isinstance(name, BotConfig):
            self.config = name
        elif scheme is None or secret is None:  # pragma: no cover
            raise ValueError("authentication scheme not defined")
        else:
            self.config = BotConfig(name=name, scheme=scheme, secret=secret)
        self.state = BotState.stopped
        self.logger = get_sub_logger(self.name)
        if log_level is not None:
            self.logger.setLevel(log_level)
        if server is not None and not isinstance(server, ServerConfig):
            server = ServerConfig.model_validate(server)
        self._server_config = server
        self._wait_list: Dict[str, asyncio.Future] = {}
        self._tid_counter = 100
        self._tasks = WeakSet()  # type: WeakSet[asyncio.Future]
        self._loop_task_ref = lambda: None

    async def hello(self, /, lang: str = "EN") -> Tuple[str, Dict[str, Any]]:
        """
        Handshake message client uses to inform the server of its version and user agent.
        This message must be the first that the client sends to the server.
        Server responds with a {ctrl} which contains server build build, wire protocol version ver,
        session ID sid in case of long polling, as well as server constraints, all in ctrl.params.
        
        :param lang: the language of the chatbot
        :type lang: str
        :return: tid and server info
        :rtype: Tuple[str, Dict[str, Any]]
        """
        tid = self._get_tid()
        user_agent = ' '.join((
            f"KaruhaBot/{APP_VERSION}",
            f"({platform.system()}/{platform.release()});",
            f"{self.server.type}-python/{LIB_VERSION}"
        ))
        ctrl = await self.send_message(
            tid,
            hi=pb.ClientHi(
                id=tid,
                user_agent=user_agent,
                ver=LIB_VERSION,
                lang=lang
            )
        )
        assert isinstance(ctrl, pb.ServerCtrl)
        if ctrl.code < 200 or ctrl.code >= 400:  # pragma: no cover
            err_text = f"fail to init chatbot: {ctrl.text}"
            self.logger.error(err_text)
            raise KaruhaBotError(err_text, bot=self, code=ctrl.code)
        params = decode_mapping(ctrl.params)
        self.server_info = params
        build = params.get("build")
        ver = params.get("ver")
        if build and ver:
            self.logger.info(f"server: {build} {ver}")
        return tid, params

    async def account(
            self,
            user_id: str,
            scheme: Optional[str] = None,
            secret: Optional[bytes] = None,
            *,
            state: Optional[str] = None,
            do_login: bool = True,
            desc: Optional[pb.SetDesc] = None,
            tags: Iterable[str] = (),
            cred: Iterable[pb.ClientCred] = (),
            extra: Optional[pb.ClientExtra] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Message {acc} creates users or updates tags or authentication credentials scheme and secret of exiting users.
        To create a new user set user to the string new optionally followed by any character sequence, e.g. newr15gsr.
        Either authenticated or anonymous session can send an {acc} message to create a new user.
        To update authentication data or validate a credential of the current user leave user unset.

        The {acc} message cannot be used to modify desc or cred of an existing user.
        Update user's me topic instead.

        :param user_id: the user id
        :type user_id: str
        :param scheme: the authentication scheme
        :type scheme: Optional[str]
        :param secret: the authentication secret
        :type secret: Optional[bytes]
        :param state: the account state
        :type state: str
        :param do_login: whether to login after updating
        :type do_login:bool
        :param desc: the account description
        :type desc: Optional[pb.SetDesc]
        :param tags: the account tags
        :type tags: Iterable[str]
        :param cred: the account credentials
        :type cred: Iterable[pb.ClientCred]
        :param extra: the extra data
        :type extra: Optional[pb.ClientExtra]
        :return: tid and params
        :rtype: Tuple[str, Dict[str, Any]]
        """
        tid = self._get_tid()
        ctrl = await self.send_message(
            tid,
            acc=pb.ClientAcc(
                id=tid,
                user_id=user_id,
                scheme=scheme,
                secret=secret,
                state=state,
                login=do_login,
                desc=desc,
                tags=tags,
                cred=cred,
            ),
            extra=extra
        )
        assert isinstance(ctrl, pb.ServerCtrl)
        if ctrl.code < 200 or ctrl.code >= 400:  # pragma: no cover
            err_text = f"fail to update account: {ctrl.text}"
            self.logger.error(err_text)
            raise KaruhaBotError(err_text, bot=self, code=ctrl.code)
        return tid, decode_mapping(ctrl.params)

    async def login(self) -> Tuple[str, Dict[str, Any]]:
        """
        Login is used to authenticate the current session.
        
        :return: tid and params
        :rtype: Tuple[str, Dict[str, Any]]
        """
        tid = self._get_tid()
        scheme, secret = await self._eval_secret()
        
        ctrl = await self.send_message(
            tid,
            login=pb.ClientLogin(
                id=tid,
                scheme=scheme,
                secret=secret
            )
        )
        assert isinstance(ctrl, pb.ServerCtrl)
        # Check for 409 "already authenticated".
        if ctrl.code == 409:  # pragma: no cover
            return tid, decode_mapping(ctrl.params)
        elif ctrl.code < 200 or ctrl.code >= 400:
            err_text = f"fail to login: {ctrl.text}"
            self.logger.error(err_text)
            # self.cancel()
            raise KaruhaBotError(err_text, bot=self, code=ctrl.code)

        self.logger.info(f"login successful (scheme {scheme})")

        params = decode_mapping(ctrl.params)
        self.account_info = params
        if "expires" in params:
            # datetime.fromisoformat before 3.11 does not support any iso 8601 format, use pydantic instead
            params["expires"] = TypeAdapter(datetime).validate_python(params["expires"])
        return tid, params

    async def subscribe(
        self, /, topic: str,
        *,
        mode: Optional[str] = None,
        get: Optional[Union[pb.GetQuery, str]] = None,
        set: Optional[pb.SetQuery] = None,
        get_since: Optional[int] = None,
        limit: int = 24,
        extra: Optional[pb.ClientExtra] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        The {sub} packet serves the following functions:

        - creating a new topic
        - subscribing user to an existing topic
        - attaching session to a previously subscribed topic
        - fetching topic data
        
        :param topic: topic to subscribe
        :type topic: str
        :param get: get query
        :type get: Optional[pb.GetQuery]
        :param get_since: get messages since this id
        :type get_since: int
        :param limit: number of messages to get
        :type limit: int
        :param extra: extra data
        :type extra: Optional[pb.ClientExtra]
        :return: tid and params
        :rtype: Tuple[str, Dict[str, Any]]
        """
        tid = self._get_tid()
        if get_since is not None:
            assert get is None, "get_since and get cannot be used at the same time"
            get = pb.GetQuery(
                data=pb.GetOpts(
                    since_id=get_since,
                    limit=limit
                ),
                what="data"
            )
        elif isinstance(get, str):
            get = pb.GetQuery(
                what=get
            )
        if mode is not None:
            assert set is None, "mode and set cannot be used at the same time"
            set = pb.SetQuery(
                sub=pb.SetSub(mode=mode)
            )
        ctrl = await self.send_message(
            tid,
            sub=pb.ClientSub(
                id=tid,
                topic=topic,
                get_query=get,
                set_query=set
            ),
            extra=extra
        )
        assert isinstance(ctrl, pb.ServerCtrl)
        if ctrl.code < 200 or ctrl.code >= 400:
            err_text = f"fail to subscribe topic {topic}: {ctrl.text}"
            self.logger.error(err_text)
            if topic == "me":  # pragma: no cover
                if ctrl.code == 502:
                    self.restart()
                else:
                    self.cancel()
            raise KaruhaBotError(err_text, bot=self, code=ctrl.code)
        else:
            self.logger.info(f"subscribe topic {topic}")
        return tid, decode_mapping(ctrl.params)

    async def leave(
        self,
        /,
        topic: str,
        *,
        unsub: bool = False,
        extra: Optional[pb.ClientExtra] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        This is a counterpart to {sub} message. It also serves two functions:

        - leaving the topic without unsubscribing (unsub=false)
        - unsubscribing (unsub=true)
        
        Server responds to {leave} with a {ctrl} packet. Leaving without unsubscribing affects just the current session.
        Leaving with unsubscribing will affect all user's sessions.

        :param topic: topic to leave
        :type topic: str
        :param extra: extra data
        :type extra: Optional[pb.ClientExtra]
        :return: tid and params
        :rtype: Tuple[str, Dict[str, Any]]
        """
        tid = self._get_tid()
        ctrl = await self.send_message(
            tid,
            leave=pb.ClientLeave(
                id=tid,
                topic=topic,
                unsub=unsub,
            ),
            extra=extra
        )
        assert isinstance(ctrl, pb.ServerCtrl)
        if ctrl.code < 200 or ctrl.code >= 400:
            err_text = f"fail to leave topic {topic}: {ctrl.text}"
            self.logger.error(err_text)
            raise KaruhaBotError(err_text, bot=self, code=ctrl.code)
        else:
            self.logger.info(f"leave topic {topic}")
        return tid, decode_mapping(ctrl.params)

    async def publish(
            self,
            /,
            topic: str,
            text: Union[str, dict],
            *,
            head: Optional[Dict[str, Any]] = None,
            extra: Optional[pb.ClientExtra] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        The message is used to distribute content to topic subscribers.

        :param topic: topic to publish
        :type topic: str
        :param text: message content
        :type text: Union[str, dict]
        :param head: message header
        :type head: Optional[Dict[str, Any]]
        :param extra: extra data
        :type extra: Optional[pb.ClientExtra]
        :return: tid and params
        :rtype: Tuple[str, Dict[str, Any]]
        """
        head = {} if head is None else encode_mapping(head)
        if "auto" not in head:
            head["auto"] = b"true"
        tid = self._get_tid()
        ctrl = await self.send_message(
            tid,
            pub=pb.ClientPub(
                id=tid,
                topic=topic,
                no_echo=True,
                head=head,
                content=to_json(text)
            ),
            extra=extra
        )
        assert isinstance(ctrl, pb.ServerCtrl)
        if ctrl.code < 200 or ctrl.code >= 400:  # pragma: no cover
            err_text = f"fail to publish message to {topic}: {ctrl.text}"
            self.logger.error(err_text)
            raise KaruhaBotError(err_text, bot=self, code=ctrl.code)
        return tid, decode_mapping(ctrl.params)

    @overload
    async def get(
        self,
        /,
        topic: str,
        what: Optional[Literal["desc"]] = None,
        *,
        desc: Optional[pb.GetOpts] = None,
        extra: Optional[pb.ClientExtra] = None,
    ) -> Tuple[str, Optional[pb.ServerMeta]]:
        """
        Query topic for description.
        
        NOTE: only one of `what` can be specified at a time
        
        :param topic: topic to get
        :type topic: str
        :param what: fields to get
        :type what: Literal["desc", "sub", "data", "tags"], optional
        :param desc: description query options
        :type desc: Optional[pb.GetOpts]
        :param extra: extra data
        :type extra: Optional[pb.ClientExtra]
        :return: tid and meta
        :rtype: Tuple[str, Optional[pb.ServerMeta]]
        """

    @overload
    async def get(
        self,
        /,
        topic: str,
        what: Optional[Literal["sub"]] = None,
        *,
        sub: Optional[pb.GetOpts] = None,
        extra: Optional[pb.ClientExtra] = None,
    ) -> Tuple[str, Optional[pb.ServerMeta]]:
        """
        Query topic for subscriptions.
        
        NOTE: only one of `what` can be specified at a time
        
        :param topic: topic to get
        :type topic: str
        :param what: fields to get
        :type what: Literal["desc", "sub", "data", "tags"], optional
        :param sub: subscriptions query options
        :type sub: Optional[pb.GetOpts]
        :param extra: extra data
        :type extra: Optional[pb.ClientExtra]
        :return: tid and meta
        :rtype: Tuple[str, Optional[pb.ServerMeta]]
        """

    @overload
    async def get(
        self,
        /,
        topic: str,
        what: Optional[Literal["data"]] = None,
        *,
        data: Optional[pb.GetOpts] = None,
        extra: Optional[pb.ClientExtra] = None,
    ) -> Tuple[str, Optional[pb.ServerMeta]]:
        """
        Query topic for data.
        
        NOTE: only one of `what` can be specified at a time
        
        :param topic: topic to get
        :type topic: str
        :param what: fields to get
        :type what: Literal["desc", "sub", "data", "tags"], optional
        :param data: data query options
        :type data: Optional[pb.GetOpts]
        :param extra: extra data
        :type extra: Optional[pb.ClientExtra]
        :return: tid and meta
        :rtype: Tuple[str, Optional[pb.ServerMeta]]
        """

    @overload
    async def get(
        self,
        /,
        topic: str,
        what: Optional[Literal["tags"]] = None,
        *,
        extra: Optional[pb.ClientExtra] = None,
    ) -> Tuple[str, Optional[pb.ServerMeta]]:
        """
        Query topic for tags.
        
        NOTE: only one of `what` can be specified at a time
        
        :param topic: topic to get
        :type topic: str
        :param what: fields to get
        :type what: Literal["desc", "sub", "data", "tags"], optional
        :param extra: extra data
        :type extra: Optional[pb.ClientExtra]
        :return: tid and meta
        :rtype: Tuple[str, Optional[pb.ServerMeta]]
        """

    @overload
    async def get(
        self,
        /,
        topic: str,
        what: Optional[Literal["cred"]] = None,
        *,
        extra: Optional[pb.ClientExtra] = None,
    ) -> Tuple[str, Optional[pb.ServerMeta]]:
        """
        Query topic for credentials.

        NOTE: only one of `what` can be specified at a time

        :param topic: topic to get
        :type topic: str
        :param what: fields to get
        :type what: Literal["cred"], optional
        :param extra: extra data
        :type extra: Optional[pb.ClientExtra]
        :return: tid and meta
        :rtype: Tuple[str, Optional[pb.ServerMeta]]
        """

    @overload
    async def get(
            self,
            /,
            topic: str,
            what: Optional[Literal["desc", "sub", "data", "tags", "cred"]] = None,
            *,
            desc: Optional[pb.GetOpts] = None,
            sub: Optional[pb.GetOpts] = None,
            data: Optional[pb.GetOpts] = None,
            extra: Optional[pb.ClientExtra] = None
    ) -> Tuple[str, Optional[pb.ServerMeta]]:
        """
        Query topic for metadata, such as description or a list of subscribers, or query message history.
        The requester must be subscribed and attached to the topic to receive the full response.
        Some limited desc and sub information is available without being attached.

        NOTE: only one of `what` can be specified at a time

        :param topic: topic to get
        :type topic: str
        :param what: fields to get
        :type what: Optional[Iterable[str]], optional
        :param desc: topic description, defaults to None
        :type desc: Optional[pb.GetOpts], optional
        :param sub: subscription info, defaults to None
        :type sub: Optional[pb.GetOpts], optional
        :param data: topic data, defaults to None
        :type data: Optional[pb.GetOpts], optional
        :param extra: extra data
        :type extra: Optional[pb.ClientExtra], optional
        :return: tid and meta
        :rtype: Tuple[str, Optional[pb.ServerMeta]]
        """

    async def get(
            self,
            /,
            topic: str,
            what: Optional[Literal["desc", "sub", "data", "tags", "cred"]] = None,
            *,
            desc: Optional[pb.GetOpts] = None,
            sub: Optional[pb.GetOpts] = None,
            data: Optional[pb.GetOpts] = None,
            extra: Optional[pb.ClientExtra] = None
    ) -> Tuple[str, Optional[pb.ServerMeta]]:
        tid = self._get_tid()
        if what is None:
            if desc is not None:
                assert sub is None and data is None
                what = "desc"
            elif sub is not None:
                assert desc is None and data is None
                what = "sub"
            elif data is not None:
                assert desc is None and sub is None
                what = "data"
            else:  # pragma: no cover
                raise ValueError("what must be specified")
        meta = await self.send_message(
            tid,
            get=pb.ClientGet(
                id=tid,
                topic=topic,
                query=pb.GetQuery(
                    what=what,
                    desc=desc,
                    sub=sub,
                    data=data
                )
            ),
            extra=extra
        )
        if isinstance(meta, pb.ServerCtrl):  # pragma: no cover
            if meta.code == 204:  # no content
                return tid, None
            err_text = f"fail to get topic {topic}: {meta.text}"
            self.logger.error(err_text)
            raise KaruhaBotError(err_text, bot=self, code=meta.code)
        assert isinstance(meta, pb.ServerMeta)
        return tid, meta

    async def get_query(
        self,
        /,
        topic: str,
        what: str,
        *,
        desc: Optional[pb.GetOpts] = None,
        sub: Optional[pb.GetOpts] = None,
        data: Optional[pb.GetOpts] = None,
        extra: Optional[pb.ClientExtra] = None
    ) -> Tuple[str, None]:
        """
        get data from a topic

        NOTE: different from `get` method, multiple fields can be specified at a time

        :param topic: topic to get
        :type topic: str
        :param what: fields to get
        :type what: str
        :param desc: topic description, defaults to None
        :type desc: Optional[pb.GetOpts], optional
        :param sub: subscription info, defaults to None
        :type sub: Optional[pb.GetOpts], optional
        :param data: topic data, defaults to None
        :type data: Optional[pb.GetOpts], optional
        :return: tid
        :rtype: Tuple[str, None]
        """
        tid = self._get_tid()
        await self.send_message(
            get=pb.ClientGet(
                id=tid,
                topic=topic,
                query=pb.GetQuery(
                    what=what,
                    desc=desc,
                    sub=sub,
                    data=data
                )
            ),
            extra=extra
        )
        return tid, None

    async def set(
            self,
            /,
            topic: str,
            *,
            desc: Optional[pb.SetDesc] = None,
            sub: Optional[pb.SetSub] = None,
            tags: Optional[Iterable[str]] = None,
            cred: Optional[pb.ClientCred] = None,
            extra: Optional[pb.ClientExtra] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Update topic metadata, delete messages or topic.
        The requester is generally expected to be subscribed and attached to the topic.
        Only desc.private and requester's sub.mode can be updated without attaching first.

        :param topic: topic to set
        :type topic: str
        :param desc: topic description, defaults to None
        :type desc: Optional[pb.SetDesc], optional
        :param sub: subscription info, defaults to None
        :type sub: Optional[pb.SetSub], optional
        :param tags: topic tags, defaults to None
        :type tags: Optional[Iterable[str]], optional
        :param cred: topic credential, defaults to None
        :type cred: Optional[pb.ClientCred], optional
        :param extra: extra data, defaults to None
        :type extra: Optional[pb.ClientExtra], optional
        :raises KaruhaBotError: fail to set topic
        :return: tid and params
        :rtype: Tuple[str, Dict[str, Any]]
        """
        tid = self._get_tid()
        ctrl = await self.send_message(
            tid,
            set=pb.ClientSet(
                id=tid,
                topic=topic,
                query=pb.SetQuery(
                    desc=desc,
                    sub=sub,
                    tags=tags,
                    cred=cred
                )
            ),
            extra=extra
        )
        assert isinstance(ctrl, pb.ServerCtrl)
        if ctrl.code < 200 or ctrl.code >= 400:  # pragma: no cover
            err_text = f"fail to set topic {topic}: {ctrl.text}"
            self.logger.error(err_text)
            raise KaruhaBotError(err_text, bot=self, code=ctrl.code)
        return tid, decode_mapping(ctrl.params)

    @overload
    async def delete(
            self,
            what: Literal["msg"],
            *,
            topic: str,
            del_seq: Iterable[pb.SeqRange] = (),
            hard: bool = False,
            extra: Optional[pb.ClientExtra] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        User can soft-delete hard=false (default) or hard-delete hard=true messages.
        Soft-deleting messages hides them from the requesting user but does not delete them from storage.
        An R permission is required to soft-delete messages.
        Hard-deleting messages deletes message content from storage (head, content) leaving a message stub.
        It affects all users. A D permission is needed to hard-delete messages.
        Messages can be deleted in bulk by specifying one or more message ID ranges in delseq parameter.
        Each delete operation is assigned a unique delete ID.
        The greatest delete ID is reported back in the clear of the {meta} message.

        :param what: delete type, defaults to "msg"
        :type what: Literal["msg"]
        :param topic: topic to delete
        :type topic: str
        :param del_seq: message ID ranges to delete, defaults to ()
        :type del_seq: Iterable[pb.SeqRange], optional
        :param hard: hard delete, defaults to False
        :type hard: bool, optional
        :param extra: extra data, defaults to None
        :type extra: Optional[pb.ClientExtra], optional
        :raises KaruhaBotError: fail to delete messages
        :return: tid and params
        :rtype: Tuple[str, Dict[str, Any]]
        """

    @overload
    async def delete(
            self,
            what: Literal["topic"],
            *,
            topic: str,
            hard: bool = False,
            extra: Optional[pb.ClientExtra] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Deleting a topic deletes the topic including all subscriptions, and all messages.
        Only the owner can delete a topic.
        
        :param what: delete type, defaults to "topic"
        :type what: Literal["topic"]
        :param topic: topic to delete
        :type topic: str
        :param hard: hard delete, defaults to False
        :type hard: bool, optional
        :param extra: extra data, defaults to None
        :type extra: Optional[pb.ClientExtra], optional
        :raises KaruhaBotError: fail to delete topic
        :return: tid and params
        :rtype: Tuple[str, Dict[str, Any]]
        """

    @overload
    async def delete(
            self,
            what: Literal["sub"],
            *,
            topic: str,
            user_id: str,
            hard: bool = False,
            extra: Optional[pb.ClientExtra] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Deleting a subscription removes specified user from topic subscribers.
        It requires an A permission. A user cannot delete own subscription.
        A {leave} should be used instead. If the subscription is soft-deleted (default),
        it's marked as deleted without actually deleting a record from storage.

        :param what: delete type, defaults to "sub"
        :type what: Literal["sub"]
        :param topic: topic to delete
        :type topic: str
        :param user_id: user ID to delete
        :type user_id: str
        :param hard: hard delete, defaults to False
        :type hard: bool, optional
        :param extra: extra data, defaults to None
        :type extra: Optional[pb.ClientExtra], optional
        :raises KaruhaBotError: fail to delete topic
        :return: tid and params
        :rtype: Tuple[str, Dict[str, Any]]
        """

    @overload
    async def delete(
            self,
            what: Literal["user"],
            *,
            user_id: str,
            hard: bool = False,
            extra: Optional[pb.ClientExtra] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Deleting a user is a very heavy operation. Use caution.
        
        :param what: delete type, defaults to "user"
        :type what: Literal["user"]
        :param user_id: user ID to delete
        :type user_id: str
        :param hard: hard delete, defaults to False
        :type hard: bool, optional
        :param extra: extra data, defaults to None
        :type extra: Optional[pb.ClientExtra], optional
        :raises KaruhaBotError: fail to delete user
        :return: tid and params
        :rtype: Tuple[str, Dict[str, Any]]
        """

    @overload
    async def delete(
            self,
            what: Literal["cred"],
            *,
            cred: pb.ClientCred,
            hard: bool = False,
            extra: Optional[pb.ClientExtra] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Delete credential.
        Validated credentials and those with no attempts at validation are hard-deleted.
        Credentials with failed attempts at validation are soft-deleted which prevents their reuse by the same user.
        
        :param what: delete type, defaults to "cred"
        :type what: Literal["cred"]
        :param cred: credential to delete
        :type cred: pb.ClientCred
        :param hard: hard delete, defaults to False
        :type hard: bool, optional
        :param extra: extra data, defaults to None
        :type extra: Optional[pb.ClientExtra], optional
        :raises KaruhaBotError: failto delete credential
        :return: tid and params
        :rtype: Tuple[str, Dict[str, Any]]
        """

    @overload
    async def delete(
            self,
            what: Literal["msg", "topic", "sub", "user", "cred"],
            *,
            topic: Optional[str] = None,
            del_seq: Iterable[pb.SeqRange] = (),
            user_id: Optional[str] = None,
            cred: Optional[pb.ClientCred] = None,
            hard: bool = False,
            extra: Optional[pb.ClientExtra] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Delete messages, subscriptions, topics, users.

        :param what: delete type
        :type what: Literal["msg", "topic", "sub", "user", "cred"]
        :param topic: topic to delete, defaults to None
        :type topic: Optional[str], optional
        :param del_seq: message ID ranges to delete, defaults to ()
        :type del_seq: Iterable[pb.SeqRange], optional
        :param user_id: user ID to delete, defaults to None
        :type user_id: Optional[str], optional
        :param cred: credential to delete, defaults to None
        :type cred: Optional[pb.ClientCred], optional
        :param hard: hard delete, defaults to False
        :type hard: bool, optional
        :param extra: extra data, defaults to None
        :type extra: Optional[pb.ClientExtra], optional
        :raises KaruhaBotError: fail to delete messages
        :return: tid and params
        :rtype: Tuple[str, Dict[str, Any]]
        """

    async def delete(
            self,
            what: Literal["msg", "topic", "sub", "user", "cred"],
            *,
            topic: Optional[str] = None,
            del_seq: Iterable[pb.SeqRange] = (),
            user_id: Optional[str] = None,
            cred: Optional[pb.ClientCred] = None,
            hard: bool = False,
            extra: Optional[pb.ClientExtra] = None
    ) -> Tuple[str, Dict[str, Any]]:
        tid = self._get_tid()
        ctrl = await self.send_message(
            tid, extra=extra, **{"del": pb.ClientDel(
                id=tid, what=getattr(pb.ClientDel.What, what.upper()),
                topic=topic,
                del_seq=del_seq,
                user_id=user_id,
                cred=cred,
                hard=hard
            )}
        )
        assert isinstance(ctrl, pb.ServerCtrl)
        if ctrl.code < 200 or ctrl.code >= 400:  # pragma: no cover
            err_text = f"fail to delete: {ctrl.text}"
            self.logger.error(err_text)
            raise KaruhaBotError(err_text, bot=self, code=ctrl.code)
        return tid, decode_mapping(ctrl.params)

    async def note_kp(self, /, topic: str) -> None:
        """key press, i.e. a typing notification.
        The client should use it to indicate that the user is composing a new message.
        
        :param topic: topic to note
        :type topic: str
        """
        await self.send_message(note=pb.ClientNote(topic=topic, what=pb.KP))

    async def note_recv(self, /, topic: str, seq: int) -> None:
        """mark a text as received
        a {data} message is received by the client software but may not yet seen by user.
        
        :param topic: topic to mark
        :type topic: str
        :param seq: sequence id
        :type seq: int
        """
        await self.send_message(note=pb.ClientNote(topic=topic, what=pb.RECV, seq_id=seq))

    async def note_read(self, /, topic: str, seq: int) -> None:
        """mark a text as read
        a {data} message is seen (read) by the user. It implies recv as well.

        :param topic: topic to mark
        :type topic: str
        :param seq: sequence id
        :type seq: int
        """
        await self.send_message(note=pb.ClientNote(topic=topic, what=pb.READ, seq_id=seq))

    async def upload(
            self,
            path: Union[str, os.PathLike, BinaryIO],
            filename: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        upload a file

        :param path: file path
        :type path: Union[str, os.PathLike]
        :raises KaruhaBotError: fail to upload file
        :return: tid and params
        :rtype: Tuple[str, Dict[str, Any]]
        """
        tid = self._get_tid()
        scheme, secret = await self._eval_secret()
        secret = base64.b64encode(secret).decode()
        params = await self.server.upload(path, f"{scheme} {secret}", tid=tid, filename=filename)
        return tid, params

    async def download(
            self,
            url: str,
            path: Union[str, os.PathLike, BinaryIO]
    ) -> Tuple[str, int]:
        """
        download a file

        :param url: file url
        :type url: str
        :param path: file path to save
        :type path: Union[str, os.PathLike]
        :raises KaruhaBotError: fail to download file
        """
        tid = self._get_tid()
        scheme, secret = await self._eval_secret()
        secret = base64.b64encode(secret).decode()
        size = await self.server.download(url, path, f"{scheme} {secret}", tid=tid)
        return tid, size

    @overload
    async def send_message(
        self,
        wait_tid: str,
        /,
        *,
        extra: Optional[pb.ClientExtra] = None,
        **kwds: Optional[Message],
    ) -> Message: ...

    @overload
    async def send_message(
        self,
        wait_tid: None = None,
        /,
        *,
        extra: Optional[pb.ClientExtra] = None,
        **kwds: Optional[Message],
    ) -> None: ...

    async def send_message(
            self,
            wait_tid: Optional[str] = None,
            /, *,
            extra: Optional[pb.ClientExtra] = None,
            **kwds: Optional[Message]
    ) -> Optional[Message]:
        """set messages to Tinode server

        :param wait_tid: if set, it will wait until a response message with the same tid is received, defaults to None
        :type wait_tid: Optional[str], optional
        :return: message which has the same tid
        :rtype: Optional[Message]
        """

        if self.state != BotState.running:
            raise KaruhaBotError("bot is not running", bot=self)
        client_msg = pb.ClientMsg(**kwds, extra=extra)  # type: ignore
        self.logger.debug(f"out: {client_msg}")
        ret = None
        if wait_tid is None:
            await self.server.send(client_msg)
        else:
            timeout = self._server_config.timeout if self._server_config is not None else 10
            with self._wait_reply(wait_tid) as future:
                await self.server.send(client_msg)
                ret = await asyncio.wait_for(future, timeout=timeout)
        for k, v in kwds.items():
            if v is None:
                continue
            for cb in self.client_event_callbacks[k]:
                cb(self, v, ret, extra)
        return ret

    async def async_run(self, server_config: Optional[ServerConfig] = None) -> None:  # pragma: no cover
        """
        run the bot in an async loop

        :param server_config: Optional server configuration. Defaults to None.
        :type server_config: Optional[ServerConfig]
        :return: None
        """
        server = server_config or self._server_config
        if server is None:
            raise ValueError("server not specified")

        if self.state == BotState.running:
            raise KaruhaBotError(f"rerun bot {self.name}", bot=self)
        elif self.state != BotState.stopped:
            raise KaruhaBotError(f"fail to run bot {self.name} (state: {self.state})", bot=self)
        self.state = BotState.running
        self._loop_task_ref = ref(asyncio.current_task())
        
        while self.state == BotState.running:
            self.logger.info(f"starting the bot {self.name}")
            async with self._run_context(server) as client:
                await self._recv_loop(client)

    @deprecated("karuha.Bot.run() is desprecated, using karuha.run() instead")
    def run(self) -> None:
        """
        run the bot

        NOTE: this method is deprecated, use karuha.run() instead
        """
        # synchronize with configuration
        try:
            get_config()
        except Exception:
            if self._server_config is None:
                raise ValueError("server not specified") from None
            init_config(
                server=self._server_config,
                bots=[self.config],
                log_level=self.logger.level
            )
        try:
            asyncio.run(self.async_run())
        except KeyboardInterrupt:
            pass
        except asyncio.CancelledError:
            raise KaruhaBotError("the connection was closed", bot=self) from None

    def cancel(self, cancel_loop: bool = True) -> None:
        if self.state in [BotState.stopped, BotState.cancelling, BotState.disabled]:
            return
        elif self.state != BotState.running:
            raise KaruhaBotError("the bot is not running", bot=self)
        self.state = BotState.cancelling
        self.logger.info(f"canceling the bot {self.name}")
        loop_task = self._loop_task_ref()
        if cancel_loop and loop_task is not None:
            loop_task.cancel()

    def restart(self) -> None:
        if self.state == BotState.disabled:
            raise KaruhaBotError(f"cannot restart disabled bot {self.name}", bot=self)
        loop_task = self._loop_task_ref()
        self.state = BotState.restarting
        if loop_task is not None:
            self.logger.info(f"restarting the bot {self.name}")
            loop_task.cancel()
        else:
            self.logger.warning(f"invalid restart operation for bot {self.name}, no valid running task found")

    @classmethod
    def from_config(cls, name: Union[str, BotConfig], /, config: Optional[Config] = None) -> Self:
        if config is None:
            config = get_config()

        if not isinstance(name, BotConfig):
            for i in config.bots:
                if i.name == name:
                    name = i
                    break
            else:
                raise ValueError(f"bot '{name}' is not in the configuration list")
        return cls(
            name,
            server=config.server,
            log_level=config.log_level
        )

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def user_id(self) -> str:
        return self.account_info["user"]
    
    @property
    def authlvl(self) -> Optional[str]:
        acc_info = getattr(self, "account_info", None)
        return acc_info and acc_info.get("authlvl")

    @property
    def token(self) -> Optional[str]:
        acc_info = getattr(self, "account_info", None)
        return acc_info and acc_info.get("token")

    @property
    def token_expires(self) -> Optional[datetime]:
        acc_info = getattr(self, "account_info", None)
        return acc_info and acc_info.get("expires")

    uid = user_id

    @property
    def server_config(self) -> ServerConfig:
        if server := getattr(self, "server", None):
            return server.config
        if self._server_config is None:
            raise AttributeError("server not specified")
        return self._server_config

    def _get_tid(self) -> str:
        tid = str(self._tid_counter)
        self._tid_counter += 1
        return tid

    @contextmanager
    def _wait_reply(self, tid: Optional[str] = None) -> Generator[asyncio.Future, None, None]:
        tid = tid or self._get_tid()
        assert tid not in self._wait_list, f"duplicated tid {tid}"
        future = asyncio.get_running_loop().create_future()
        self._wait_list[tid] = future
        try:
            yield future
        except asyncio.TimeoutError:
            raise KaruhaTimeoutError(f"timeout while waiting for reply from bot {self.name}") from None
        finally:
            assert self._wait_list.pop(tid, None) is future

    def _set_reply_message(self, tid: str, message: Any) -> None:
        f = self._wait_list.get(tid)
        if f is not None and not f.done():
            f.set_result(message)

    def _create_task(self, coro: Coroutine, /) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        return task
    
    async def _eval_secret(self) -> Tuple[str, bytes]:
        try:
            scheme, secret = self.config.scheme, self.config.secret
            if self.token is not None and (
                self.token_expires is None
                or self.token_expires > datetime.now(timezone.utc)
            ):
                scheme, secret = "token", base64.b64decode(self.token.encode())
            elif scheme == "cookie":
                scheme, secret = await read_auth_cookie(self.config.secret)
        except Exception as e:  # pragma: no cover
            err_text = f"fail to read auth secret: {e}"
            self.logger.error(err_text)
            raise KaruhaBotError(err_text, bot=self) from e
        if isinstance(secret, str):
            secret = secret.encode()
        return scheme, secret

    async def _prepare_account(self) -> None:
        try:
            await self.hello()
        except Exception:
            self.logger.error("failed to connect to server, restarting")
            self.restart()
            return

        if not self.config.auto_login:
            self.logger.info("auto login is disabled, skipping")
            return

        retry = self._server_config.retry if self._server_config is not None else 0
        for i in range(retry):
            try:
                await self.login()
            except (asyncio.TimeoutError, KaruhaBotError):
                self.logger.warning(f"login failed, retrying {i+1} times")
            else:
                break
        else:
            try:
                await self.login()
            except (asyncio.TimeoutError, KaruhaBotError):
                self.logger.error("login failed, cancel the bot")
                self.cancel()

        await self.subscribe(
            "me",
            get="sub desc tags cred"
        )

    @asynccontextmanager
    async def _run_context(self, server_config: ServerConfig, /) -> AsyncGenerator[BaseServer, None]:  # pragma: no cover
        server_type = get_server_type(self.config.connect_mode or server_config.connect_mode)
        self.server = server_type(server_config, self.logger)

        try:
            self.initialize_event_callback(self)
            await self.server.start()
            yield self.server
        except KaruhaServerError:
            self.logger.error(f"disconnected from {server_config.host}, retrying...", exc_info=sys.exc_info())
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            if self.state == BotState.running:
                self.cancel(cancel_loop=False)
                raise
        except:  # noqa: E722
            self.cancel(cancel_loop=False)
            raise
        finally:
            try:
                await self.server.stop()
                await self.finalize_event_callback(self)
            except Exception:
                self.logger.exception("error while finalizing event callback", exc_info=True)
            except asyncio.CancelledError:
                pass

            if self.state == BotState.restarting:
                # uncancel from Bot.restart()
                self.state = BotState.running
            elif self.state == BotState.cancelling:
                # shutdown from Bot.cancel()
                self.state = BotState.stopped

            for t in self._tasks:
                t.cancel()

    async def _recv_loop(self, server: BaseServer) -> None:
        async for message in server:
            self.logger.debug(f"in: {message}")

            for desc, msg in message.ListFields():
                for e in self.server_event_callbacks[desc.name]:
                    e(self, msg)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_plain_validator_function(
            lambda x: x if isinstance(x, source_type) else cls(x)
        )

    def __repr__(self) -> str:
        state = self.state.name
        uid = getattr(self, "user_id", 'unknown uid')
        return f"<bot {self.name} ({uid}) {state}>"


class ProxyBot(Bot):
    """
    the bot that runs on the `extra.on_behalf_of` proxy
    """
    __slots__ = ["on_behalf_of"]

    def __init__(self, *args: Any, on_behalf_of: str, **kwds: Any) -> None:
        super().__init__(*args, **kwds)
        self.on_behalf_of = on_behalf_of
    
    @classmethod
    def from_bot(cls, bot: Bot, /, on_behalf_of: str, name: Optional[str] = None) -> Self:
        config = bot.config.model_copy()
        if name is None:
            config.name = f"{config.name}_proxy_{on_behalf_of}"
        else:
            config.name = name
        return cls(config, bot._server_config, bot.logger.level, on_behalf_of=on_behalf_of)
    
    @overload
    async def send_message(
        self,
        wait_tid: str,
        /,
        *,
        extra: Optional[pb.ClientExtra] = None,
        **kwds: Optional[Message],
    ) -> Message: ...

    @overload
    async def send_message(
        self,
        wait_tid: None = None,
        /,
        *,
        extra: Optional[pb.ClientExtra] = None,
        **kwds: Optional[Message],
    ) -> None: ...

    async def send_message(
            self,
            wait_tid: Optional[str] = None,
            /, *,
            extra: Optional[pb.ClientExtra] = None,
            **kwds: Optional[Message]
    ) -> Optional[Message]:
        """set messages to Tinode server

        :param wait_tid: if set, it willl wait until a response message with the same tid is received, defaults to None
        :type wait_tid: Optional[str], optional
        :param extra: extra fields, defaults to None
        :type extra: Optional[pb.ClientExtra], optional
        :return: message which has the same tid
        :rtype: Optional[Message]
        """
        exclude_msg = {"hi", "login"}
        keys = set(kwds)
        if exclude_keys := keys & exclude_msg:
            if len(exclude_keys) != len(keys):
                raise KaruhaBotError("cannot mix message types", bot=self)
        elif extra is None:
            extra = pb.ClientExtra(on_behalf_of=self.on_behalf_of)
        elif not extra.on_behalf_of:
            extra.on_behalf_of = self.on_behalf_of
        elif extra.on_behalf_of != self.on_behalf_of:
            raise KaruhaBotError(f"on_behalf_of mismatch: {extra.on_behalf_of} != {self.on_behalf_of}", bot=self)
        return await super().send_message(wait_tid, extra=extra, **kwds)
    
    @property
    def user_id(self) -> str:
        return self.on_behalf_of
    
    uid = user_id

    @property
    def login_user_id(self) -> str:
        return super().user_id


async def read_auth_cookie(cookie_file_name: Union[str, bytes, os.PathLike]) -> Tuple[str, Union[str, bytes]]:
    """Read authentication token from a file"""
    async with aio_open(cookie_file_name, 'r') as cookie:
        params = from_json(await cookie.read())
    scheme = params.get("scheme")
    secret = params.get('secret')
    if scheme is None or secret is None:
        raise ValueError("invalid cookie file")
    if scheme == 'token':
        secret = base64.b64decode(secret)
    return scheme, secret
