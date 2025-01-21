# Karuha

[![License](https://img.shields.io/github/license/Ovizro/Karuha.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/KaruhaBot.svg)](https://pypi.python.org/pypi/KaruhaBot)
[![Build Status](https://github.com/Ovizro/Karuha/actions/workflows/test_cov.yml/badge.svg)](https://github.com/Ovizro/Karuha/actions)
![PyPI - Downloads](https://img.shields.io/pypi/dw/KaruhaBot)
![Python Version](https://img.shields.io/badge/python-3.8%20|%203.9%20|%203.10%20|%203.11%20|%203.12-blue.svg)

A simple Tinode chat bot framework

**Language: English/[中文](README_cn.md)**

The name of the library `Karuha` comes from the character Karuha Ramkone (カルハ・ラムコネ) in the game Starry Sky Train and White's Journey.

<div align="center">

![Karuha](https://raw.githubusercontent.com/Visecy/Karuha/master/docs/img/tw_icon-karuha2.png)

</div>

> カルハ・ラムコネと申します。カルハちゃんって呼んでいいわよ

## Installation

Install from Pypi:

    pip install KaruhaBot

Install from Pypi:

    git clone https://github.com/Visecy/Karuha.git
    cd Karuha
    make install

## Quick Start

Before you begin, you need to ensure that the Tinode service is running locally with the default gRPC port 16060.

> If your service is not local or the gRPC port has changed, you may need to modify or add server configuration items in the following code.

Create a new file `config.json` and write the following content as the configuration file:

```json
{
    "server": {
        "host": "localhost:16060",
        "web_host": "http://localhost:6060"
    },
    "bots": [
        {
            "name": "chatbot",
            "scheme": "basic",
            "secret": "{chatbot_login_name}:{chatebot_login_passwd}"
        }
    ]
}
```

> Replace `{chatbot_login_name}` and `{chatebot_login_passwd}` with the login account name and password of the chatbot on the Tinode server.

Use the following command to start the chatbot:

    python -m Karuha ./config.json

You can now view messages sent to the chatbot from others in the command line.

## User Interaction

Receiving messages alone is certainly not enough; we need to interact with users. Karuha provides a powerful command system. With the command system, we can easily receive messages from users and respond accordingly.

### Simple Command Example

Let's start with the simplest command. We want to implement a `hi` command that replies `Hello!` when the bot receives this command.

Create a new `hi.py` and write the following content in it:

```python
from karuha import on_command, MessageSession


@on_command
async def hi(session: MessageSession) -> None:
    await session.send("Hello!")
```

The above code involves some Python knowledge, and I will briefly introduce each one. If you are already familiar with this knowledge, you can skip this part.

In the first line of the code, we import the `on_command` decorator and the `MessageSession` class from the `karuha` module. A decorator is an object that can be used to modify functions or classes. Here, its usage is shown in the fourth line, where it decorates the function by using `@on_command` before the function definition. The decorated function will be registered as a command and will be called when the corresponding message is received.

Next is the definition of the `hi` function. Here we use `async def` to define the command function. Unlike regular functions defined with `def`, functions defined with `async def` are asynchronous functions. Asynchronous programming is a relatively complex topic, and it's okay if you don't understand it; here we will only use some simple syntax similar to normal functions.

You might be a bit unfamiliar with the line `(session: MessageSession) -> None`. This is a type annotation that specifies the parameter type and return type of the function. Here we declare the type of `session` as `MessageSession`, and the return type as `None`, meaning there is no return value. In Python, type annotations are optional, but for commands in Karuha, they are used for parsing message data. While not mandatory, it is recommended to add type annotations when writing commands to help Karuha better understand your code.

Next is the content of the function, which is very short, only one line. `session` is a session object that encapsulates many APIs for receiving and sending messages. Here, we use the `send` method to send messages. `send` is an asynchronous method, so it needs to be preceded by `await` when called.

After completing the command writing, we can run the robot to test it. Use the following command to run the robot:

```sh
python -m karuha ./config.json -m hi
```

Then, in the conversation with the robot, enter the following content:

    /hi

> By default, karuha will only process text messages starting with `/` as commands. This behavior can be set before defining all commands using the `set_prefix` function.

If all goes well, you should see the robot reply with `Hello!`.

### Example Extension

In the above example, we did not directly use the user's input. What should I do if I want to get the user's input?

One method is to use the message log in `session`. The complete user input is contained in `session.last_message`. But this is not very elegant.

A more convenient method is to directly modify the function signature, for example: 

```python
from typing import List

@on_command
async def hi(session: MessageSession, argv: List[str]) -> None:
    ...
```

We added an `argv` parameter, of type `List[str]`, which represents the user input. Let's slightly modify the content of the `hi` function: 

```python
@on_command
async def hi(session: MessageSession, argv: List[str]) -> None:
    if nor argv:
        await session.send("Hello!")
        return
    name = argv[0]
    await session.send(f"Hello {name}!")
```

In the above code, we added the name to greet in the command's reply content based on the previous logic.

Let's run the bot and try sending it the following: 

    /hi world

You will receive `Hello world!` returned by the bot.

## About More

Of course, the API provided by Karuha is not limited to these; if you are interested in more content, you can refer to the library's source code.

### Features and Support

The functionalities that have been implemented so far are as follows: 

- [X] Command system
- [X] Rich text (Drafty) parsing
- [X] Rule-based chat message processing
- [X] User and topic information reading✨
- [X] Proxy sending bot✨
- [X] Tinode plugin server✨
- [X] Client low-level API encapsulation
  - [X] `hi` message
  - [X] `acc` message
  - [X] `login` message
  - [X] `sub` message
  - [X] `leave` message
  - [X] `pub` message
  - [X] `get` message
  - [X] `set` message
  - [X] `del` message
  - [X] `note` message
- [X] Server-side low-level API handling
  - [X] `data` message
  - [X] `ctrl` message
  - [X] `meta` message
  - [X] `pres` message
  - [X] `info` message
- [X] Large file upload and download ✨

> Items marked with ✨ are experimental features, and their functionality may have issues that require further experimentation and feedback. The interfaces for these features may also undergo breaking changes in the future.

Possible features to be added next include:

- [ ] User and topic information modification
- [ ] Audio attachment upload support
- [ ] Video attachment upload support
- [ ] The underlying API encapsulation based on http and websocket
- [ ] Automatic parsing of command parameters in argparse format
- [ ] Refactor the store module using sqlalchemy

### Module Development

Currently, karuha's support for module development is relatively simple. There is no dedicated API for defining chatbot modules, but it can support presetting some commands.

The way to define commands in external modules is similar to the normal definition method. However, to avoid affecting the user's related command settings, we need to create a new command collection (CommandCollection). The method to create a command collection and define commands within it is as follows:

```python
from typing import List

from karuha import MessageSession
from karuha.command import new_collection, add_sub_collection


collection = new_collection()
add_sub_collection(collection)


@collection.on_command
async def hi(session: MessageSession, argv: List[str]) -> None:
    ...
```

> Note: In order for the command collection to take effect, you need to call the `add_sub_collection` function to add the command collection to the sub-command collection.

### Architecture Description

The overall architecture of Karuha is as follows:

| Interface Level | Provided Module  | Function               |
| -------- | -------------- | ------------------ |
| Upper Level     | karuha.command    | Command Registration and Processing     |
| Middle Level    | karuha.event      | Asynchronous Event-Driven System   |
| Lower Level     | karuha.bot        | Basic Encapsulation of Tinode API |

In addition, there are also some relatively independent modules:

| Module                 | Function                                   |
| -------------------- | -------------------------------------- |
| karuha.text          | Text processing module                     |
| karuha.config        | Configuration file parsing module         |
| karuha.plugin_server | Plugin module used by the Tinode server, not enabled by default |

### Message Processing

Karuha provides two complementary message processing systems, namely the asynchronous message event system (event) and the message dispatcher system (dispatcher).

The asynchronous message event is used to receive and process messages in parallel. By registering message event handlers, relevant information about messages can be quickly collected. Different message handlers operate in parallel and do not interfere with each other.

The message dispatcher is located downstream of the asynchronous message event system, used to determine the final message handler. This system is used to bridge the middle-layer event system and the upper-layer command system. If you wish to provide feedback to users based on message content and avoid interference from other message processing modules, you should use this system.

## About the Documentation

There are no plans for comprehensive documentation for this project. There will be no documentation for this project in the foreseeable future. If you wish to provide documentation for this project, I would be very grateful.

## About Contributions

You are welcome to raise your questions and suggestions in the issues. If you are interested in contributing to the development of the Tinode chatbot, you are welcome to participate.
