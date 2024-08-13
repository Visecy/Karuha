"""
Tino, Tinode's chatbot.

A karuha implementation for Tino.

Run with:

    python tino.py --login-basic alice:alice123

Or:

    python -m karuha ./config.json --module tino
"""

import asyncio
import random
from pathlib import Path
from argparse import ArgumentParser

from aiofiles import open as aio_open

import karuha
from karuha import MessageSession, on_rule


_quotes = None
_quotes_path = Path(__file__).parent / "quotes.txt"
_quotes_lock = asyncio.Lock()


async def get_quotes():
    """lazy load quotes"""
    global _quotes
    if _quotes is not None:
        return _quotes
    async with _quotes_lock:
        if _quotes is not None:
            return _quotes
        async with aio_open(_quotes_path, "r") as f:
            content = await f.read()
        _quotes = content.splitlines()
        print(f"Loaded {len(_quotes)} quotes")
    return _quotes


@on_rule()
async def quote(session: MessageSession) -> None:
    """
    Reply with a random quote for each message.
    """
    quotes = await get_quotes()
    await session.send(random.choice(quotes))


if __name__ == "__main__":
    purpose = "Tino, Tinode's chatbot."
    parser = ArgumentParser(description=purpose)
    parser.add_argument('--host', default='localhost:16060', help='address of Tinode server gRPC endpoint')
    parser.add_argument('--ssl', action='store_true', help='use SSL to connect to the server')
    parser.add_argument('--ssl-host', help='SSL host name to use instead of default (useful for connecting to localhost)')
    parser.add_argument('--listen', default=None, help='address to listen on for incoming Plugin API calls')
    parser.add_argument('--login-basic', help='login using basic authentication username:password')
    parser.add_argument('--login-token', help='login using token authentication')
    parser.add_argument('--login-cookie', default='.tn-cookie', help='read credentials from the provided cookie file')
    parser.add_argument('--quotes', default=_quotes_path, type=Path, help='file with messages for the chatbot to use, one message per line')
    
    namespace = parser.parse_args()
    if namespace.login_basic:
        login_schema = "basic"
        login_secret = namespace.login_basic
    elif namespace.login_token:
        login_schema = "token"
        login_secret = namespace.login_token
    elif namespace.login_cookie:
        login_schema = "cookie"
        login_secret = namespace.login_cookie
    else:
        raise ValueError("No login method specified")
    
    karuha.init_config(
        server=karuha.ServerConfig(
            host=namespace.host,
            ssl=namespace.ssl,
            ssl_host=namespace.ssl_host,
            enable_plugin=bool(namespace.listen),
            listen=namespace.listen or "0.0.0.0:40051"
        ),
        bots=[
            karuha.BotConfig(  # type: ignore
                name="chatbot",
                schema=login_schema,
                secret=login_secret
            )
        ]
    )
    _quotes_path = namespace.quotes
    karuha.run()
