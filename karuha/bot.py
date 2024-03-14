import asyncio
import platform
import sys
from asyncio.queues import Queue
from base64 import b64decode
from collections import defaultdict
from contextlib import asynccontextmanager, contextmanager
from enum import IntEnum
from typing import (Any, AsyncGenerator, Callable, Coroutine, Dict, Generator, Iterable,
                    List, Literal, Optional, Tuple, Union, overload)
from weakref import WeakSet, ref

import grpc
from aiofiles import open as aio_open
from google.protobuf.message import Message
from grpc import aio as grpc_aio
from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema
from tinode_grpc import pb
from typing_extensions import Self, deprecated

from .config import Bot as BotConfig
from .config import Config
from .config import Server as ServerConfig
from .config import get_config, init_config
from .logger import Level, get_sub_logger
from .version import APP_VERSION, LIB_VERSION
from .utils.decode import decode_mapping, encode_mapping, json


class State(IntEnum):
    disabled = 0
    running = 1
    stopped = 2
    restarting = 3


class Bot(object):
    """
    the core class of the chatbot

    Provides many low-level API interfaces.
    """
    __slots__ = [
        "queue", "state", "client", "logger", "config", "server",
        "_wait_list", "_tid_counter", "_tasks", "_loop_task_ref"
    ]

    initialize_event_callback: Callable[[Self], Any]
    finalize_event_callback: Callable[[Self], Coroutine]
    server_event_callbacks: Dict[str, List[Callable[[Self, Message], Any]]] = defaultdict(list)
    client_event_callbacks: Dict[str, List[Callable[[Self, Message, Optional[Message]], Any]]] = defaultdict(list)

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
        self.state = State.stopped
        self.logger = get_sub_logger(self.name)
        if log_level is not None:
            self.logger.setLevel(log_level)
        if server is not None and not isinstance(server, ServerConfig):
            server = ServerConfig.model_validate(server)
        self.server = server
        self._wait_list: Dict[str, asyncio.Future] = {}
        self._tid_counter = 100
        self._tasks = WeakSet()  # type: WeakSet[asyncio.Future]
        self._loop_task_ref = lambda: None

    async def hello(self, /, lang: str = "EN") -> Tuple[str, Dict[str, Any]]:
        """
        send a hello message to the server and get the server id
        
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

    async def login(self) -> Tuple[str, Dict[str, Any]]:
        """
        login to the server and get the user id
        
        :return: tid and params
        :rtype: Tuple[str, Dict[str, Any]]
        """
        tid = self._get_tid()
        schema, secret = self.config.schema_, self.config.secret
        try:
            if schema == "cookie":
                schema, secret = await read_auth_cookie(self.config.secret)
            else:
                secret = secret.encode("ascii")
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
            self.cancel()
            raise KaruhaBotError(err_text, bot=self, code=ctrl.code)

        self.logger.info("login successful")

        params = ctrl.params
        if not params:
            return tid, {}
        if "user" in params:
            self.config.user = json.loads(params["user"].decode())
        # if "token" in params:
        #     self.config.schema_ = "token"
        #     self.config.secret = json.loads(params["token"].decode())
        return tid, decode_mapping(params)

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
        subscribe to a topic
        
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
        leave a topic

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
        publish message to a topic

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
        if head is None:
            head = {}
        else:
            head = encode_mapping(head)
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
                content=json.dumps(text).encode()
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
            extra: Optional[pb.ClientExtra] = None
    ) -> Tuple[str, Optional[pb.ServerMeta]]: ...

    @overload
    async def get(
            self,
            /,
            topic: str,
            what: Optional[Literal["sub"]] = None,
            *,
            sub: Optional[pb.GetOpts] = None,
            extra: Optional[pb.ClientExtra] = None
    ) -> Tuple[str, Optional[pb.ServerMeta]]: ...

    @overload
    async def get(
            self,
            /,
            topic: str,
            what: Optional[Literal["data"]] = None,
            *,
            data: Optional[pb.GetOpts] = None,
            extra: Optional[pb.ClientExtra] = None
    ) -> Tuple[str, Optional[pb.ServerMeta]]: ...

    @overload
    async def get(
            self,
            /,
            topic: str,
            what: Literal["tags"],
            *,
            extra: Optional[pb.ClientExtra] = None
    ) -> Tuple[str, Optional[pb.ServerMeta]]: ...

    @overload
    async def get(
            self,
            /,
            topic: str,
            what: Literal["cred"],
            *,
            extra: Optional[pb.ClientExtra] = None
    ) -> Tuple[str, Optional[pb.ServerMeta]]: ...

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
        get data from a topic

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
        set data to a topic

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

    async def note_read(self, /, topic: str, seq: int) -> None:
        await self.send_message(note=pb.ClientNote(topic=topic, what=pb.READ, seq_id=seq))

    @overload
    async def send_message(self, wait_tid: str, /, **kwds: Optional[Message]) -> Message: ...

    @overload
    async def send_message(self, wait_tid: None = None, /, **kwds: Optional[Message]) -> None: ...

    async def send_message(self, wait_tid: Optional[str] = None, /, **kwds: Optional[Message]) -> Optional[Message]:
        """set messages to Tinode server

        :param wait_tid: if set, it willl wait until a response message with the same tid is received, defaults to None
        :type wait_tid: Optional[str], optional
        :return: message which has the same tid
        :rtype: Optional[Message]
        """

        if self.state != State.running:
            raise KaruhaBotError("bot is not running", bot=self)
        client_msg = pb.ClientMsg(**kwds)  # type: ignore
        ret = None
        if wait_tid is None:
            await self.queue.put(client_msg)
        else:
            with self._wait_reply(wait_tid) as future:
                await self.queue.put(client_msg)
                ret = await future
        for k, v in kwds.items():
            if v is None:
                continue
            for cb in self.client_event_callbacks[k]:
                cb(self, v, ret)
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
        while self.state == State.running:
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
        
        :rtype: None
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
        if self.state in [State.stopped, State.disabled]:
            return
        self.state = State.stopped
        self.logger.info(f"canceling the bot {self.name}")
        loop_task = self._loop_task_ref()
        if cancel_loop and loop_task is not None:
            loop_task.cancel()

    def restart(self) -> None:
        if self.state == State.disabled:
            raise KaruhaBotError(f"cannot restart disabled bot {self.name}", bot=self)
        loop_task = self._loop_task_ref()
        self.state = State.restarting
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
        uid = self.config.user
        if uid is None:
            raise ValueError(f"cannot fetch the uid of bot {self.name}")
        return uid

    def _get_tid(self) -> str:
        tid = str(self._tid_counter)
        self._tid_counter += 1
        return tid

    @contextmanager
    def _wait_reply(self, tid: Optional[str] = None) -> Generator[Coroutine, None, None]:
        if self.server:
            timeout = self.server.timeout
        else:
            timeout = 10
        tid = tid or self._get_tid()
        future = asyncio.get_running_loop().create_future()
        self._wait_list[tid] = future
        try:
            yield asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            raise KaruhaTimeoutError(f"timeout while waiting for reply from bot {self.name}") from None
        finally:
            assert self._wait_list.pop(tid, None) is future

    def _create_task(self, coro: Coroutine, /) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        return task

    def _prepare_loop_task(self) -> None:
        if self.state == State.running:
            raise KaruhaBotError(f"rerun bot {self.name}", bot=self)
        elif self.state != State.stopped:
            raise KaruhaBotError(f"fail to run bot {self.name} (state: {self.state})", bot=self)
        self.state = State.running
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
            if self.state == State.restarting:
                # uncancel from Bot.restart()
                self.state = State.running
            else:
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
            self.server = old_server_config
            
            # clean up for restarting
            while not self.queue.empty():
                self.queue.get_nowait()

            for t in self._tasks:
                t.cancel()

    async def _message_generator(self) -> AsyncGenerator[pb.ClientMsg, None]:  # pragma: no cover
        while True:
            assert self.state == State.running
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
            lambda x: x if isinstance(x, source_type) else Bot(x)
        )

    def __repr__(self) -> str:
        state = self.state.name
        uid = self.config.user or ''
        host = self.server.host if self.server else 'unknown'
        return f"<bot {self.name} ({uid}) {state} on host {host}>"


def get_stream(channel: grpc_aio.Channel, /) -> grpc_aio.StreamStreamMultiCallable:  # pragma: no cover
    return channel.stream_stream(
        '/pbx.Node/MessageLoop',
        request_serializer=pb.ClientMsg.SerializeToString,
        response_deserializer=pb.ServerMsg.FromString
    )


async def read_auth_cookie(cookie_file_name) -> Union[Tuple[str, bytes], Tuple[None, None]]:
    """Read authentication token from a file"""
    async with aio_open(cookie_file_name, 'r') as cookie:
        params = json.loads(await cookie.read())
    schema = params.get("schema")
    secret = params.get('secret')
    if schema is None or secret is None:
        return None, None
    if schema == 'token':
        secret = b64decode(secret)
    else:
        secret = secret.encode('utf-8')
    return schema, secret


from .exception import KaruhaBotError, KaruhaTimeoutError
