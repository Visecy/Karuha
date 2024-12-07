import asyncio
import base64
import os
import platform
import sys
from asyncio.queues import Queue
from collections import defaultdict
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from enum import IntEnum
from io import IOBase, TextIOBase
from typing import (Any, AsyncGenerator, Callable, Coroutine, Dict, Generator,
                    Iterable, List, Literal, Optional, Tuple, Union, overload)
from weakref import WeakSet, ref

import grpc
from aiofiles import open as aio_open
from aiofiles.threadpool.binary import AsyncBufferedIOBase
from aiohttp import ClientError, ClientSession, ClientTimeout, FormData
from google.protobuf.message import Message
from grpc import aio as grpc_aio
from pydantic import GetCoreSchemaHandler, TypeAdapter
from pydantic_core import CoreSchema, core_schema, from_json, to_json
from tinode_grpc import pb
from typing_extensions import Self, deprecated

from .config import Bot as BotConfig
from .config import Config
from .config import Server as ServerConfig
from .config import get_config, init_config
from .logger import Level, get_sub_logger
from .utils.context import nullcontext
from .utils.decode import decode_mapping, encode_mapping
from .version import APP_VERSION, LIB_VERSION


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
        "queue", "state", "client", "logger", "config", "server", "user_id", "token", "token_expires", "authlvl",
        "_wait_list", "_tid_counter", "_tasks", "_loop_task_ref"
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
        schema: Literal["basic", "token", "cookie"],
        secret: str,
        *,
        server: Union[ServerConfig, Any, None] = None,
        log_level: Level = ...
    ) -> None:
        """
        :param name: the bot name
        :type name: str
        :param schema: the authentication scheme
        :type schema: Literal["basic", "token", "cookie"]
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
        schema: Optional[Literal["basic", "token", "cookie"]] = None,
        secret: Optional[str] = None,
        *,
        server: Union[ServerConfig, Any, None] = None,
        log_level: Optional[Level] = None
    ) -> None:
        if isinstance(name, BotConfig):
            self.config = name
        elif schema is None or secret is None:
            raise ValueError("authentication scheme not defined")
        else:
            self.config = BotConfig(name=name, schema=schema, secret=secret)
        self.state = BotState.stopped
        self.logger = get_sub_logger(self.name)
        if log_level is not None:
            self.logger.setLevel(log_level)
        if server is not None and not isinstance(server, ServerConfig):
            server = ServerConfig.model_validate(server)
        self.server = server
        self.token: Optional[str] = None
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
            f"gRPC-python/{LIB_VERSION}"
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
        build = ctrl.params["build"].decode()
        ver = ctrl.params["ver"].decode()
        if build:
            self.logger.info(f"server: {build} {ver}")
        return tid, decode_mapping(ctrl.params)

    async def account(
            self,
            user_id: str,
            scheme: Optional[str] = None,
            secret: Optional[bytes] = None,
            *,
            state: str = "ok",
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
        schema, secret = self.config.schema_, self.config.secret
        try:
            if self.token is not None and self.token_expires > datetime.now(timezone.utc):
                schema, secret = "token", base64.b64decode(self.token.encode())
            elif schema == "cookie":
                schema, secret = await read_auth_cookie(self.config.secret)
            else:
                secret = secret.encode()
        except Exception as e:  # pragma: no cover
            err_text = f"fail to read auth secret: {e}"
            self.logger.error(err_text)
            self.cancel()
            raise KaruhaBotError(err_text, bot=self) from e
        ctrl = await self.send_message(
            tid,
            login=pb.ClientLogin(
                id=tid,
                scheme=schema,
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

        self.logger.info(f"login successful (schema {schema})")

        params = decode_mapping(ctrl.params)
        if "user" in params:
            self.user_id = params["user"]
        if "token" in params:
            self.token = params["token"]
            # datetime.fromisoformat before 3.11 does not support any iso 8601 format, use pydantic instead
            self.token_expires = TypeAdapter(datetime).validate_python(params["expires"])
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

    async def leave(self, /, topic: str, *, extra: Optional[pb.ClientExtra] = None) -> Tuple[str, Dict[str, Any]]:
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
                topic=topic
            ),
            extra=extra
        )
        assert isinstance(ctrl, pb.ServerCtrl)
        if ctrl.code < 200 or ctrl.code >= 400:
            err_text = f"fail to leave topic {topic}: {ctrl.text}"
            self.logger.error(err_text)
            if topic == "me":  # pragma: no cover
                if ctrl.code == 502:
                    self.restart()
                else:
                    self.cancel()
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
        if ctrl.code < 200 or ctrl.code >= 400:
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
            else:
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
            path: Union[str, os.PathLike, IOBase]
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

        try:
            async with await self._get_http_session() as session:
                self.logger.debug(f"upload request: {tid=} {path=} {session.headers=}")
                while True:
                    url = "/v0/file/u/"
                    data = FormData()
                    data.add_field("id", tid)
                    if isinstance(path, IOBase):
                        path.seek(0)
                        cm = nullcontext(path)
                        _path = None
                    else:
                        cm = open(path, "rb")
                        _path = os.path.basename(path)
                    with cm as f:
                        data.add_field("file", f, filename=_path)
                        async with session.post(url, data=data) as resp:
                            ret = await resp.text()
                    self.logger.debug(f"upload response: {ret}")
                    ctrl = from_json(ret)["ctrl"]
                    params = ctrl["params"]
                    code = ctrl["code"]
                    if code != 307:
                        break
                    url = params["url"]
                    # If 307 Temporary Redirect is returned, the client must retry the upload at the provided URL.
                    self.logger.info(f"upload redirected to {url}")
        except OSError as e:
            raise KaruhaBotError(f"fail to read file {path}", bot=self) from e
        except ClientError as e:
            err_text = f"fail to upload file {path}: {e}"
            self.logger.error(err_text, exc_info=True)
            raise KaruhaBotError(err_text, bot=self) from e
        assert ctrl["id"] == tid, "tid mismatch"
        if code < 200 or code >= 400:  # pragma: no cover
            err_text = f"fail to upload file {path}: {ctrl['text']}"
            self.logger.error(err_text)
            raise KaruhaBotError(err_text, bot=self, code=code)
        self.logger.info(f"upload file {path}")
        return tid, params

    async def download(
            self,
            url: str,
            path: Union[str, os.PathLike, IOBase]
    ) -> None:
        """
        download a file

        :param url: file url
        :type url: str
        :param path: file path to save
        :type path: Union[str, os.PathLike]
        :raises KaruhaBotError: fail to download file
        """
        tid = self._get_tid()
        if isinstance(path, IOBase):
            path.seek(0)
            cm = nullcontext(path)
        else:
            cm = aio_open(path, "wb")
        try:
            async with await self._get_http_session() as session, cm as f:
                self.logger.debug(f"download request: {tid=} {path=} {session.headers=}")
                size = 0
                async with session.get(url, params={"id": tid}) as resp:
                    resp.raise_for_status()
                    async for chunk in resp.content.iter_any():
                        size += len(chunk)
                        if isinstance(f, AsyncBufferedIOBase):
                            await f.write(chunk)
                        elif isinstance(f, TextIOBase):
                            f.write(chunk.decode())
                        else:
                            f.write(chunk)
            self.logger.debug(f"download length: {size}")
        except OSError as e:
            raise KaruhaBotError(f"fail to write file {path}", bot=self) from e
        except ClientError as e:
            err_text = f"fail to download file {path}: {e}"
            self.logger.error(err_text, exc_info=True)
            raise KaruhaBotError(err_text, bot=self) from e
        self.logger.info(f"download file {path}")

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
        ret = None
        if wait_tid is None:
            await self.queue.put(client_msg)
        else:
            timeout = self.server.timeout if self.server is not None else 10
            with self._wait_reply(wait_tid) as future:
                await self.queue.put(client_msg)
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
        server = server_config or self.server
        if server is None:
            raise ValueError("server not specified")

        self._prepare_loop_task()
        while self.state == BotState.running:
            self.logger.info(f"starting the bot {self.name}")
            async with self._run_context(server) as channel:
                stream = get_stream(channel)  # type: ignore
                msg_gen = self._message_generator()
                client = stream(msg_gen)
                await self._loop(client)

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
            if self.server is None:
                raise ValueError("server not specified") from None
            init_config(
                server=self.server,
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
    def uid(self) -> str:
        return self.user_id

    def _get_tid(self) -> str:
        tid = str(self._tid_counter)
        self._tid_counter += 1
        return tid

    async def _get_http_session(self) -> ClientSession:
        if self.server is None:
            raise ValueError("server not specified")
        web_host = self.server.web_host

        try:
            schema, secret = self.config.schema_, self.config.secret
            if self.token is not None and self.token_expires > datetime.now(timezone.utc):
                schema, secret = "token", self.token
            elif schema == "cookie":
                schema, secret_bytes = await read_auth_cookie(secret)
                secret = base64.b64encode(secret_bytes).decode()
            else:
                secret = base64.b64encode(secret.encode()).decode()
        except Exception as e:  # pragma: no cover
            err_text = f"fail to read auth secret: {e}"
            self.logger.error(err_text)
            raise KaruhaBotError(err_text, bot=self) from e

        headers = {
            'X-Tinode-APIKey': self.server.api_key,
            "X-Tinode-Auth": f"{schema.title()} {secret}",
            "User-Agent": f"KaruhaBot {APP_VERSION}/{LIB_VERSION}",
        }
        return ClientSession(str(web_host), headers=headers, timeout=ClientTimeout(self.server.timeout))

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
        
        retry = self.server.retry if self.server is not None else 0
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

    def _prepare_loop_task(self) -> None:
        if self.state == BotState.running:
            raise KaruhaBotError(f"rerun bot {self.name}", bot=self)
        elif self.state != BotState.stopped:
            raise KaruhaBotError(f"fail to run bot {self.name} (state: {self.state})", bot=self)
        self.state = BotState.running
        self.queue = Queue()
        self._loop_task_ref = ref(asyncio.current_task())

    def _get_channel(self, server_config: ServerConfig, /) -> grpc_aio.Channel:  # pragma: no cover
        host = server_config.host
        secure = server_config.ssl
        ssl_host = server_config.ssl_host
        if not secure:
            self.logger.info(f"connecting to server at {host}")
            return grpc_aio.insecure_channel(host)
        opts = (('grpc.ssl_target_name_override', ssl_host),) if ssl_host else None
        self.logger.info(f"connecting to secure server at {host} SNI={ssl_host or host}")
        return grpc_aio.secure_channel(host, grpc.ssl_channel_credentials(), opts)

    @asynccontextmanager
    async def _run_context(self, server_config: ServerConfig, /) -> AsyncGenerator[grpc_aio.Channel, None]:  # pragma: no cover
        channel = self._get_channel(server_config)
        old_server_config = self.server
        self.server = server_config
        try:
            self.initialize_event_callback(self)
            yield channel
        except grpc.RpcError:
            self.logger.error(f"disconnected from {server_config.host}, retrying...", exc_info=sys.exc_info())
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            if self.state == BotState.restarting:
                # uncancel from Bot.restart()
                self.state = BotState.running
            elif self.state == BotState.running:
                self.cancel(cancel_loop=False)
                raise
        except:  # noqa: E722
            self.cancel(cancel_loop=False)
            raise
        finally:
            try:
                await channel.close()
                await self.finalize_event_callback(self)
            except Exception:
                self.logger.exception("error while finalizing event callback", exc_info=True)
            except asyncio.CancelledError:
                pass
            self.state = BotState.stopped
            self.server = old_server_config

            # clean up for restarting
            while not self.queue.empty():
                self.queue.get_nowait()

            for t in self._tasks:
                t.cancel()

    async def _message_generator(self) -> AsyncGenerator[pb.ClientMsg, None]:  # pragma: no cover
        while True:
            assert self.state == BotState.running
            msg: pb.ClientMsg = await self.queue.get()
            self.logger.debug(f"out: {msg}")
            yield msg

    async def _loop(self, client: grpc_aio.StreamStreamCall) -> None:  # pragma: no cover
        message: pb.ServerMsg
        async for message in client:  # type: ignore
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
        host = self.server.host if self.server else 'unknown'
        return f"<bot {self.name} ({uid}) {state} on host {host}>"


class ProxyBot(Bot):
    """
    the bot that runs on the `extra.on_behalf_of` proxy
    """
    __slots__ = ["on_behalf_of", "login_user_id"]

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
        return cls(config, bot.server, bot.logger.level, on_behalf_of=on_behalf_of)
    
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

    @user_id.setter
    def user_id(self, val: str) -> None:
        self.login_user_id = val


def get_stream(channel: grpc_aio.Channel, /) -> grpc_aio.StreamStreamMultiCallable:  # pragma: no cover
    return channel.stream_stream(
        '/pbx.Node/MessageLoop',
        request_serializer=pb.ClientMsg.SerializeToString,
        response_deserializer=pb.ServerMsg.FromString
    )


async def read_auth_cookie(cookie_file_name: Union[str, os.PathLike]) -> Tuple[str, bytes]:
    """Read authentication token from a file"""
    async with aio_open(cookie_file_name, 'r') as cookie:
        params = from_json(await cookie.read())
    schema = params.get("schema")
    secret = params.get('secret')
    if schema is None or secret is None:
        raise ValueError("invalid cookie file")
    if schema == 'token':
        secret = base64.b64decode(secret)
    else:
        secret = secret.encode('utf-8')
    return schema, secret


from .exception import KaruhaBotError, KaruhaTimeoutError
