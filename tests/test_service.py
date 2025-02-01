from karuha.service import BaseService
from .utils import AsyncBotTestCase, new_test_message


class ServiceTestCase(AsyncBotTestCase):
    def test_base(self) -> None:
        msg = new_test_message()

        def f(base_svc: BaseService) -> BaseService:
            return base_svc

        self.assertEqual(msg.call_handler(f).bot, msg.bot)
