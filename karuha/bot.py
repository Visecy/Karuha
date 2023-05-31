import asyncio
import json
import platform
from asyncio.queues import Queue, QueueEmpty
from contextlib import contextmanager
from enum import IntEnum
from typing import (Any, AsyncGenerator, Coroutine, Dict, Literal, Optional,
                    Union, overload)
from typing_extensions import Self
from weakref import WeakSet, ref

import grpc
from grpc import aio as grpc_aio
from google.protobuf.message import Message
from tinode_grpc import pb

from . import WORKDIR
from .config import Bot as BotConfig, Config, Server as ServerConfig
from .event import _get_server_event
from .exception import KaruhaConnectError
from .logger import get_logger
from .version import APP_VERSION, LIB_VERSION


class State(IntEnum):
    disabled = 0
    running = 1
    stopped = 2


class Bot(object):
    __slots__ = [
        "queue", "state", "client", "logger", "config", "server", "subscriptions",
        "_wait_list", "_tid_counter", "_tasks", "_loop_task_ref"
    ]
    
    @overload
    def __init__(
        self,
        config: BotConfig,
        /, *,
        server: Union[ServerConfig, Any, None] = None,
        log_level: str = ...
    ) -> None: ...
    @overload  # noqa: E301
    def __init__(
        self, name: str, /,
        schema: Literal["basic", "token", "cookie"],
        secret: str,
        *,
        server: Union[ServerConfig, Any, None] = None,
        log_level: str = ...
    ) -> None: ...
    def __init__(  # noqa: E301
        self,
        name: Union[str, BotConfig],
        /,
        schema: Optional[Literal["basic", "token", "cookie"]] = None,
        secret: Optional[str] = None,
        *,
        server: Union[ServerConfig, Any, None] = None,
        log_level: str = "INFO"
    ) -> None:
        if isinstance(name, BotConfig):
            self.config = name
        elif schema is None or secret is None:
            raise ValueError("authentication scheme not defined")
        else:
            self.config = BotConfig(name=name, schema=schema, secret=secret)
        self.queue = Queue()
        self.state = State.stopped
        self.logger = get_logger(f"KARUHA/{self.name}", WORKDIR / self.name / "log")
        self.logger.setLevel(log_level)
        if server is None:
            server = ServerConfig()
        elif not isinstance(server, ServerConfig):
            server = ServerConfig.parse_obj(server)
        self.server = server
        self.subscriptions = set()
        self._wait_list: Dict[str, asyncio.Future] = {}
        self._tid_counter = 100
        self._tasks = WeakSet()
        self._loop_task_ref = lambda: None
    
    async def hello(self, /, lang: str = "EN") -> None:
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
        if ctrl.code < 200 or ctrl.code >= 400:
            self.logger.error(f"fail to init chatbot: {ctrl.text}")
        build = ctrl.params["build"].decode()
        ver = ctrl.params["ver"].decode()
        self.logger.info(f"server: {build} {ver}")
    
    async def login(self) -> None:
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
        if ctrl.code == 409:
            return
        elif ctrl.code < 200 or ctrl.code >= 400:
            self.logger.error(f"fail to login: {ctrl.text}")
            self.cancel()
            return
        
        self.logger.info("login successful")
        self._create_task(self.subscribe("me"))

        params = ctrl.params
        if not params:
            return
        if "user" in params:
            self.config.user = json.loads(params["user"].decode())
        if "token" in params:
            self.config.schema_ = "token"
            self.config.secret = json.loads(params["token"].decode())
    
    async def subscribe(self, /, topic: str) -> None:
        if topic in self.subscriptions:
            return
        tid = self._get_tid()
        ctrl = await self.send_message(
            tid,
            sub=pb.ClientSub(
                id=tid,
                topic=topic
            )
        )
        assert isinstance(ctrl, pb.ServerCtrl)
        if ctrl.code < 200 or ctrl.code >= 400:
            self.logger.error(f"fail to subscribe topic {topic}: {ctrl.text}")
            if topic == "me":
                if ctrl.code == 502:
                    self.restart()
                else:
                    self.cancel()
        else:
            self.subscriptions.add(topic)
            self.logger.info(f"subscribe topic {topic}")
    
    async def leave(self, /, topic: str) -> None:
        if topic not in self.subscriptions:
            return
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
            self.subscriptions.remove(topic)
            self.logger.info(f"leave topic {topic}")
    
    async def publish(self, /, topic: str, text: Union[str, dict], *, head: Optional[Dict[str, Any]] = None) -> None:
        if head is None:
            head = {"auto": b"true"}
        else:
            head = {k: json.dumps(v).encode() for k, v in head.items()}
        tid = self._get_tid()
        await self.send_message(
            pub=pb.ClientPub(
                id=tid,
                topic=topic,
                no_echo=True,
                head=head,
                content=json.dumps(text).encode()
            )
        )
        self.logger.info(f"<= {text} ({topic})")
    
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
        client_msg = pb.ClientMsg(**kwds)
        if wait_tid is None:
            return await self.queue.put(client_msg)
        future = asyncio.get_running_loop().create_future()
        self._wait_list[wait_tid] = future
        try:
            await self.queue.put(client_msg)
            rsp_msg = await future
        except:  # noqa: E722
            self._wait_list.pop(wait_tid, None)
            raise
        else:
            assert self._wait_list.pop(wait_tid) == future
        return rsp_msg

    async def async_run(self) -> None:
        assert self.state == State.stopped
        server = self.server
        while True:
            try:
                async with self._get_channel(server.host, server.ssl, server.ssl_host) as channel:
                    stream = get_stream(channel)  # type: ignore
                    msg_gen = self._message_generator()
                    self._tasks.add(msg_gen)
                    self.client = stream(msg_gen)
                    await self._loop()
            except grpc.RpcError:
                self.logger.error(f"disconnected from {server.host}, retrying...")
                await asyncio.sleep(0.2)
            except KeyboardInterrupt:
                break
    
    def run(self) -> None:
        try:
            asyncio.run(self.async_run())
        except KeyboardInterrupt:
            pass
        except asyncio.CancelledError:
            raise KaruhaConnectError("the connection was closed by remote") from None
    
    def cancel(self, cancel_loop: bool = True) -> None:
        if self.state != State.running:
            return
        self.state = State.stopped
        self.logger.info(f"canceling the bot {self.name}")
        while True:
            try:
                self.queue.get_nowait()
            except QueueEmpty:
                break
        self.subscriptions.clear()
        for i in self._wait_list.values():
            i.cancel()
        map(asyncio.Task.cancel, self._tasks)
        loop_task = self._loop_task_ref()
        if cancel_loop and loop_task is not None:
            loop_task.cancel()
    
    def restart(self) -> None:
        loop_task = self._loop_task_ref()
        if loop_task is not None:
            loop_task.set_exception(
                KaruhaConnectError("restart chatbot")
            )
    
    @classmethod
    def from_config(cls, name: Union[str, BotConfig], /, config: Config) -> Self:
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
    
    def _create_task(self, coro: Coroutine, /) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        return task
    
    def _get_channel(self, /, host: str, secure: bool = False, ssl_host: Optional[str] = None) -> grpc_aio.Channel:
        if not secure:
            self.logger.info(f"connecting to server at {host}")
            return grpc_aio.insecure_channel(host)
        opts = (('grpc.ssl_target_name_override', ssl_host),) if ssl_host else None
        self.logger.info(f"connecting to secure server at {host} SNI={ssl_host or host}")
        return grpc_aio.secure_channel(host, grpc.ssl_channel_credentials(), opts)
    
    @contextmanager
    def _run_context(self):
        assert self.state == State.stopped
        self.state = State.running
        self._loop_task_ref = ref(asyncio.current_task())
        self.logger.info(f"starting the bot {self.name}")
        try:
            yield self
        except:  # noqa: E722
            self.cancel(cancel_loop=False)
            raise
    
    async def _message_generator(self) -> AsyncGenerator[Message, None]:
        while True:
            msg: Message = await self.queue.get()
            self.logger.debug(f"out: {msg}")
            yield msg
    
    async def _loop(self) -> None:
        with self._run_context():
            self._create_task(self.hello())
            self._create_task(self.login())
            
            message: pb.ServerMsg
            async for message in self.client:  # type: ignore
                self.logger.debug(f"in {message}")

                for desc, msg in message.ListFields():
                    for e in _get_server_event(desc.name):
                        e(self, msg).trigger(self._create_task)


def get_stream(channel: grpc_aio.Channel, /) -> grpc_aio.StreamStreamMultiCallable:
    return channel.stream_stream(
        '/pbx.Node/MessageLoop',
        request_serializer=pb.ClientMsg.SerializeToString,
        response_deserializer=pb.ServerMsg.FromString
    )
