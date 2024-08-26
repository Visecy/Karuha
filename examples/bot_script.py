import signal
import asyncio
import contextlib
from weakref import ref

from karuha.bot import Bot, State, get_stream
from karuha.config import load_config
from karuha.event.bot import BotInitEvent
from karuha.exception import KaruhaBotError
from karuha.runner import _handle_sigterm

async def run_bot_loop(bot):
    bot._loop_task_ref = ref(asyncio.current_task())
    while bot.state == State.running:
        bot.logger.info(f"starting the bot {bot.name}")
        async with bot._run_context(bot.server) as channel:
            stream = get_stream(channel)  # type: ignore
            msg_gen = bot._message_generator()
            client = stream(msg_gen)
            await bot._loop(client)

async def run_hello(bot):
    tid, params = await bot.hello()
    print(tid, params)

async def run_subscribe(bot):
    tid, params = await bot.subscribe("topic_test")
    print(tid, params)

async def run_create_account(bot: Bot, name: str):
    try:
        tid, params = await bot.account(
            scheme = 'basic',
            secret = f'{name}:test123',
            fn = 'Test User',
            tags = 'test,test-user',
            auth = 'JRWPA',
            anon = 'JW',
            cred = 'email:test@example.com',
            do_login=True
        )
        print(tid, params)
    except KaruhaBotError as e:
        print(e)

async def run_bot_prepare(bot):
    print("start run_bot_prepare")
    bot._prepare_loop_task()

async def run_bot_init(bot):
    Bot.initialize_event_callback = BotInitEvent.new_and_wait
    await bot.initialize_event_callback(bot)

async def main():
    config = load_config()
    _loop = asyncio.get_running_loop()
    _loop.set_debug(enabled=True)
    with contextlib.suppress(NotImplementedError):
        _loop.add_signal_handler(signal.SIGTERM, _handle_sigterm)

    for i in range(153, 160):
        print("i:", i)
        # create a bot without login
        bot = Bot.from_config(config.bots[0], config)
        await _loop.create_task(run_bot_prepare(bot))
        print("BOT prepare finished")
        task_loop = _loop.create_task(run_bot_loop(bot))
        await _loop.create_task(run_bot_init(bot))
        await _loop.create_task(run_create_account(bot, f'test{i}'))
        bot.cancel()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):  # pragma: no cover
        pass
