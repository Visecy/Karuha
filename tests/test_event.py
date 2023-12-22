import asyncio
from unittest import IsolatedAsyncioTestCase

from karuha.event import Event, on

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
    
    def test_dispatcher(self) -> None:
        ...
