"""
Send a welcome message to new users.

NOTE: Running this example requires enabling the plugin server

Run with:

    python -m karuha ./config.json --module exec

"""

import json

from karuha import BaseSession
from karuha.event.plugin import AccountCreateEvent, on_new_account


@on_new_account
async def welcome(event: AccountCreateEvent, session: BaseSession) -> None:
    user_name = "new user"
    if event.action:
        public = json.loads(event.public)
        if isinstance(public, dict) and "fn" in public:
            user_name = public["fn"]
    await session.send(f"Hello {user_name}, welcome to Tinode!")
