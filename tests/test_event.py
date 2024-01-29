import asyncio
from unittest import IsolatedAsyncioTestCase

from karuha.event import Event, on
from karuha.dispatcher import AbstractDispatcher, FutureDispatcher

from .utils import EventCatcher


class TestEvent(IsolatedAsyncioTestCase):
    async def test_init(self) -> None:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        event = Event()

        @on(Event)
        async def hdl(ev: Event) -> None:
            future.set_result(ev)
        
        self.assertEqual(len(await event.trigger()), 1)
        self.assertTrue(future.done())
        self.assertIs(future.result(), event)

        Event.remove_handler(hdl)
    
    async def test_catcher(self) -> None:
        hdl_num = len(Event.__handlers__)
        with EventCatcher(Event) as catcher:
            self.assertEqual(len(Event.__handlers__), hdl_num + 1)
            self.assertIs(Event.__handlers__[-1], catcher)
            self.assertFalse(catcher.caught)

            e = Event.new()
            self.assertFalse(catcher.caught)
            self.assertIs(await catcher.catch_event(), e)
            self.assertFalse(catcher.caught)
            with self.assertRaises(IndexError):
                catcher.catch_event_nowait()

            e = Event()
            await e.trigger()
            self.assertTrue(catcher.caught)
            self.assertIs(catcher.catch_event_nowait(), e)
            self.assertFalse(catcher.caught)

        self.assertEqual(len(Event.__handlers__), hdl_num)

    async def test_dispatcher(self) -> None:
        class DispatcherTester(AbstractDispatcher[Event]):
            __slots__ = ["message", "match_rate"]

            def __init__(self, match_rate: float, *, once: bool = False) -> None:
                super().__init__(once=once)
                self.message = None
                self.match_rate = match_rate
            
            def match(self, message: Event) -> float:
                return self.match_rate

            def run(self, message: Event) -> None:
                self.message = message
            
            def reset(self) -> None:
                self.message = None
            
            @property
            def received(self) -> bool:
                return self.message is not None
            
        DispatcherTester.dispatch(Event())
        
        d1 = DispatcherTester(1, once=True)
        d2 = DispatcherTester(0.5)

        d2.activate()
        DispatcherTester.dispatch(Event())
        self.assertTrue(d2.received)
        
        d1.activate()
        d2.reset()
        DispatcherTester.dispatch(Event())
        self.assertTrue(d1.received)
        self.assertFalse(d2.received)

        DispatcherTester.dispatch(Event())
        self.assertIn(d2, DispatcherTester.dispatchers)
        self.assertFalse(d1.activated)
        self.assertTrue(d2.received)

        with DispatcherTester(2) as d3:
            self.assertFalse(d3.received)
            DispatcherTester.dispatch(Event())
            self.assertTrue(d3.received)
        
        self.assertNotIn(d3, DispatcherTester.dispatchers)
        d3.deactivate()
    
    async def test_future_dispatcher(self) -> None:
        class FutureDispatcherTester(FutureDispatcher[Event]):
            __slots__ = ["match_rate"]

            def __init__(self, /, future: asyncio.Future, match_rate: float, *, once: bool = False) -> None:
                super().__init__(future, once=once)
                self.match_rate = match_rate
            
            def match(self, message: Event) -> float:
                return self.match_rate
            
            @property
            def received(self) -> bool:
                return self.future.done()
        
        loop = asyncio.get_running_loop()
        d1 = FutureDispatcherTester(loop.create_future(), 1)
        d2 = FutureDispatcherTester(loop.create_future(), 0.5)

        with d1, d2:
            e = Event()
            FutureDispatcherTester.dispatch(e)
            self.assertFalse(d2.received)
            self.assertTrue(d1.received)
            self.assertIs(d1.future.result(), e)
