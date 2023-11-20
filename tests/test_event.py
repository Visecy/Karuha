import asyncio
from unittest import IsolatedAsyncioTestCase

from karuha.event import Event, on


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
