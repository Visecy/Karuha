import asyncio
from contextlib import contextmanager
import json
import platform
from asyncio.queues import Queue, QueueEmpty
from enum import IntEnum
from weakref import WeakSet, ref
from typing import AsyncGenerator, Coroutine, Dict, Literal, Optional, Union, overload

import grpc
from google.protobuf.message import Message
from tinode_grpc import pb

from .config import LoginInfo, Server, get_config
from .event import _get_server_event
from .exception import KaruhaConnectError
from .logger import logger
from .stream import get_channel, get_stream
from .version import APP_VERSION, LIB_VERSION


class State(IntEnum):
    disabled = 0
    running = 1
    stopped = 2


class Bot(object):
    __slots__ = ["queue", "state", "client", "login_info", "_wait_list", "_tid_counter", "_tasks", "_loop_task_ref"]
    
    def __init__(
        self,
        name: Union[str, LoginInfo],
        /,
        schema: Optional[Literal["basic", "token", "cookie"]] = None,
        secret: Optional[str] = None
    ) -> None:
        if isinstance(name, LoginInfo):
            self.login_info = name
        elif schema is None or secret is None:
            raise ValueError("authentication scheme not defined")
        else:
            self.login_info = LoginInfo(name=name, schema=schema, secret=secret)
        self.queue = Queue()
        self.state = State.stopped
        self._wait_list: Dict[str, asyncio.Future] = {}
        self._tid_counter = 100
        self._tasks = WeakSet()
        self._loop_task_ref = lambda: None
    
    async def hello(self, lang: str = "EN") -> None:
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
            logger.error(f"fail to init chatbot: {ctrl.text}")
        build = ctrl.params["build"].decode()
        ver = ctrl.params["ver"].decode()
        logger.info(f"server: {build} {ver}")
    
    async def login(self) -> None:
        tid = self._get_tid()
        ctrl = await self.send_message(
            tid,
            login=pb.ClientLogin(
                id=tid,
                scheme=self.login_info.schema_,
                secret=self.login_info.secret.encode("ascii")
            )
        )
        assert isinstance(ctrl, pb.ServerCtrl)
        if ctrl.code == 409:
            return
        if ctrl.code < 200 or ctrl.code >= 400:
            logger.error(f"fail to login: {ctrl.text}")
            self.cancel()
            return
        
        logger.info("login successful")
        self._create_task(self.subscribe("me"))

        params = ctrl.params
        if not params:
            return
        if "user" in params:
            self.login_info.user = json.loads(params["user"].decode()) 
        if "token" in params:
            self.login_info.schema_ = "token"
            self.login_info.secret = json.loads(params["token"].decode())
    
    async def subscribe(self, topic: str) -> None:
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
            logger.error(f"fail to subscribe topic {topic}: {ctrl.text}")
            if topic == "me":
                if ctrl.code == 502:
                    self.restart()
                else:
                    self.cancel()
        else:
            logger.info(f"subscribe topic {topic}")
    
    @overload
    async def send_message(self, wait_tid: str, **kwds: Message) -> Message: ...
    @overload
    async def send_message(self, wait_tid: None = None, **kwds: Message) -> None: ...

    async def send_message(self, wait_tid: Optional[str] = None, **kwds: Message) -> Optional[Message]:
        client_msg = pb.ClientMsg(**kwds)
        if wait_tid is None:
            return await self.queue.put(client_msg)
        future = asyncio.get_running_loop().create_future()
        self._wait_list[wait_tid] = future
        try:
            await self.queue.put(client_msg)
            rsp_msg = await future
        except:
            self._wait_list.pop(wait_tid, None)
            raise
        else:
            assert self._wait_list.pop(wait_tid) == future
        return rsp_msg

    async def async_run(self, server: Server) -> None:
        assert self.state == State.stopped
        while True:
            try:
                async with get_channel(server.host, server.ssl, server.ssl_host) as channel:
                    stream = get_stream(channel)  # type: ignore
                    self.client = stream(self._message_generator())
                    await self._loop()
            except grpc.RpcError:
                logger.error(f"disconnected from {server.host}, retrying...")
                await asyncio.sleep(0.2)
            except KeyboardInterrupt:
                break
    
    def run(self, server: Optional[Server] = None) -> None:
        server = server or get_config().server
        try:
            asyncio.run(self.async_run(server))
        except KeyboardInterrupt:
            pass
    
    def cancel(self, cancel_loop: bool = True) -> None:
        if self.state != State.running:
            return
        self.state = State.stopped
        logger.info(f"canceling the bot {self.name}")
        while True:
            try:
                self.queue.get_nowait()
            except QueueEmpty:
                break
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

    @property
    def name(self) -> str:
        return self.login_info.name
    
    @property
    def uid(self) -> str:
        uid = self.login_info.user
        if uid is None:
            raise ValueError(f"cannot fetch the uid of bot {self.name}")
        return uid
    
    def _get_tid(self) -> str:
        tid = str(self._tid_counter)
        self._tid_counter += 1
        return tid
    
    def _create_task(self, coro: Coroutine) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        return task
    
    @contextmanager
    def _run_context(self):
        assert self.state == State.stopped
        self.state = State.running
        self._loop_task_ref = ref(asyncio.current_task())
        logger.info(f"starting the bot {self.name}")
        try:
            yield self
        except:
            self.cancel(cancel_loop=False)
            raise
    
    async def _message_generator(self) -> AsyncGenerator[Message, None]:
        while True:
            msg: Message = await self.queue.get()
            logger.debug(f"out: {msg}")
            yield msg
    
    async def _loop(self) -> None:
        with self._run_context():
            message: pb.ServerMsg
            self._create_task(self.hello())
            self._create_task(self.login())
            async for message in self.client:  # type: ignore
                logger.debug(f"in {message}")
                for desc, msg in message.ListFields():
                    for e in _get_server_event(desc.name):
                        self._create_task(
                            e(self, msg)()
                        )
    