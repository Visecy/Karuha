import asyncio
import json
import platform
import sys
from asyncio.queues import Queue
from collections import defaultdict
from contextlib import asynccontextmanager, contextmanager
from enum import IntEnum
from typing import (Any, AsyncGenerator, Callable, Coroutine, Dict, Generator,
                    List, Literal, Optional, Union, overload)
from weakref import WeakSet, ref

import grpc
from google.protobuf.message import Message
from grpc import aio as grpc_aio
from tinode_grpc import pb
from typing_extensions import Self, deprecated

from .config import Bot as BotConfig
from .config import Config
from .config import Server as ServerConfig
from .config import get_config, init_config
from .exception import KaruhaBotError
from .logger import Level, get_sub_logger
from .version import APP_VERSION, LIB_VERSION


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
    
    async def hello(self, /, lang: str = "EN") -> str:
        """
        send a hello message to the server and get the server id
        
        :param lang: the language of the chatbot
        :type lang: str
        :return: tid
        :rtype: str
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
            self.logger.error(f"fail to init chatbot: {ctrl.text}")
            return tid
        build = ctrl.params["build"].decode()
        ver = ctrl.params["ver"].decode()
        if build:
            self.logger.info(f"server: {build} {ver}")
        return tid
    
    async def login(self) -> str:
        """
        login to the server and get the user id
        
        :return: tid
        :rtype: str
        """
        tid = self._get_tid()
        ctrl = await self.send_message(
            tid,
            login=pb.ClientLogin(
                id=tid,
                scheme=self.config.schema_,
                secret=self.config.secret.encode("ascii")
            )
        )
        assert isinstance(ctrl, pb.ServerCtrl)
        if ctrl.code == 409:  # pragma: no cover
            return tid
        elif ctrl.code < 200 or ctrl.code >= 400:
            self.logger.error(f"fail to login: {ctrl.text}")
            self.cancel()
            return tid
        
        self.logger.info("login successful")

        params = ctrl.params
        if not params:
            return tid
        if "user" in params:
            self.config.user = json.loads(params["user"].decode())
        if "token" in params:
            self.config.schema_ = "token"
            self.config.secret = json.loads(params["token"].decode())
        return tid
    
    async def subscribe(self, /, topic: str, *, get_since: Optional[int] = None, limit: int = 24) -> str:
        """
        subscribe to a topic
        
        :param topic: topic to subscribe
        :type topic: str
        :param get_since: get messages since this id
        :type get_since: int
        :param limit: number of messages to get
        :type limit: int
        :return: tid
        :rtype: str
        """
        tid = self._get_tid()
        if get_since is not None:
            query = pb.GetQuery(
                data=pb.GetOpts(
                    since_id=get_since,
                    limit=limit
                ),
                what="data"
            )
        else:
            query = None
        ctrl = await self.send_message(
            tid,
            sub=pb.ClientSub(
                id=tid,
                topic=topic,
                get_query=query
            )
        )
        assert isinstance(ctrl, pb.ServerCtrl)
        if ctrl.code < 200 or ctrl.code >= 400:
            self.logger.error(f"fail to subscribe topic {topic}: {ctrl.text}")
            if topic == "me":  # pragma: no cover
                if ctrl.code == 502:
                    self.restart()
                else:
                    self.cancel()
        else:
            self.logger.info(f"subscribe topic {topic}")
        return tid
    
    async def leave(self, /, topic: str) -> str:
        """
        leave a topic

        :param topic: topic to leave
        :type topic: str
        :return: tid
        :rtype: str
        """
        tid = self._get_tid()
        ctrl = await self.send_message(
            tid,
            leave=pb.ClientLeave(
                id=tid,
                topic=topic
            )
        )
        assert isinstance(ctrl, pb.ServerCtrl)
        if ctrl.code < 200 or ctrl.code >= 400:
            self.logger.error(f"fail to leave topic {topic}: {ctrl.text}")
            if topic == "me":
                if ctrl.code == 502:
                    self.restart()
                else:
                    self.cancel()
        else:
            self.logger.info(f"leave topic {topic}")
        return tid
    
    async def publish(self, /, topic: str, text: Union[str, dict], *, head: Optional[Dict[str, Any]] = None) -> str:
        """
        publish message to a topic

        :param topic: topic to publish
        :type topic: str
        :param text: message content
        :type text: Union[str, dict]
        :param head: message header
        :type head: Optional[Dict[str, Any]]
        :return: tid or None
        :rtype: str
        """
        if head is None:
            head = {}
        else:
            head = {k: json.dumps(v).encode() for k, v in head.items()}
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
            )
        )
        assert isinstance(ctrl, pb.ServerCtrl)
        if ctrl.code < 200 or ctrl.code >= 400:
            self.logger.error(f"fail to publish message to {topic}: {ctrl.text}")
        return tid
    
    async def note_read(self, /, topic: str, seq: int) -> None:
        await self.send_message(note=pb.ClientNote(topic=topic, what=pb.READ, seq_id=seq))
    
    @overload
    async def send_message(self, wait_tid: str, /, **kwds: Message) -> Message: ...
    @overload
    async def send_message(self, wait_tid: None = None, /, **kwds: Message) -> None: ...

    async def send_message(self, wait_tid: Optional[str] = None, /, **kwds: Message) -> Optional[Message]:
        """set a message to Tinode server

        :param wait_tid: if set, it willl wait until a response message with the same tid is received, defaults to None
        :type wait_tid: Optional[str], optional
        :return: message which has the same tid
        :rtype: Optional[Message]
        """
        if self.state != State.running:
            raise KaruhaBotError("bot is not running")
        client_msg = pb.ClientMsg(**kwds)  # type: ignore
        ret = None
        if wait_tid is None:
            await self.queue.put(client_msg)
        else:
            with self._wait_reply(wait_tid) as future:
                await self.queue.put(client_msg)
                ret = await future
        for k, v in kwds.items():
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
            try:
                async with self._run_context() as channel:
                    stream = get_stream(channel)  # type: ignore
                    msg_gen = self._message_generator()
                    client = stream(msg_gen)
                    await self._loop(client)
            except grpc.RpcError:
                self.logger.error(f"disconnected from {server.host}, retrying...", exc_info=sys.exc_info())
                await asyncio.sleep(0.5)
            except KeyboardInterrupt:
                break
            except asyncio.CancelledError:
                if self.state == State.restarting:
                    # uncancel from Bot.restart()
                    self.state = State.running
                else:
                    raise
    
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
            raise KaruhaBotError("the connection was closed") from None
    
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
            raise KaruhaBotError(f"cannot restart disabled bot {self.name}")
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
    def _wait_reply(self, tid: Optional[str] = None) -> Generator[asyncio.Future, None, None]:
        tid = tid or self._get_tid()
        future = asyncio.get_running_loop().create_future()
        self._wait_list[tid] = future
        try:
            yield future
        finally:
            assert self._wait_list.pop(tid, None) is future

    def _create_task(self, coro: Coroutine, /) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        return task

    def _prepare_loop_task(self) -> None:
        if self.state == State.running:
            raise KaruhaBotError(f"rerun bot {self.name}")
        elif self.state != State.stopped:
            raise KaruhaBotError(f"fail to run bot {self.name} (state: {self.state})")
        self.state = State.running
        self.queue = Queue()
        self._loop_task_ref = ref(asyncio.current_task())
    
    def _get_channel(self) -> grpc_aio.Channel:  # pragma: no cover
        assert self.server
        host = self.server.host
        secure = self.server.ssl
        ssl_host = self.server.ssl_host
        if not secure:
            self.logger.info(f"connecting to server at {host}")
            return grpc_aio.insecure_channel(host)
        opts = (('grpc.ssl_target_name_override', ssl_host),) if ssl_host else None
        self.logger.info(f"connecting to secure server at {host} SNI={ssl_host or host}")
        return grpc_aio.secure_channel(host, grpc.ssl_channel_credentials(), opts)
    
    @asynccontextmanager
    async def _run_context(self) -> AsyncGenerator[grpc_aio.Channel, None]:  # pragma: no cover
        channel = self._get_channel()
        try:
            yield channel
        except:  # noqa: E722
            await channel.close()
            if self.state != State.restarting:
                self.cancel(cancel_loop=False)
            raise
        finally:
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
        self._create_task(self.hello())
        self._create_task(self.login())
        
        message: pb.ServerMsg
        async for message in client:  # type: ignore
            self.logger.debug(f"in: {message}")

            for desc, msg in message.ListFields():
                for e in self.server_event_callbacks[desc.name]:
                    e(self, msg)
    
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
