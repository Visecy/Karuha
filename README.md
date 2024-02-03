# Karuha

[![License](https://img.shields.io/github/license/Ovizro/Karuha.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/KaruhaBot.svg)](https://pypi.python.org/pypi/KaruhaBot)
![Python Version](https://img.shields.io/badge/python-3.8%20|%203.9%20|%203.10%20|%203.11-blue.svg)

A simple Tinode chatbot framework.

The name of the library `Karuha` comes from the character Karuha Ramukone (カルハ・ラムコネ) in the game 星空鉄道とシロの旅.

<center>

![Karuha](https://raw.githubusercontent.com/Visecy/Karuha/master/docs/img/tw_icon-karuha2.png)

</center>

> カルハ・ラムコネと申します。カルハちゃんって呼んでいいわよ

## Installation

From pip:

    pip install KaruhaBot

From source code:

    git clone https://github.com/Ovizro/Karuha.git
    cd Karuha
    make install

## Quick Start

Before starting, you need to make sure you have the Tinode service running locally with its gRPC port set to the default value of 16060.

> If your service is not local or the gRPC port has been changed, you may need to modify or add additional server configuration items in the following code.

Create a new file config.json and write the configuration in it:

```json
{
    "server": {
        "host": "localhost:16060",
    },
    "bots": [
        {
            "name": "chatbot",
            "schema": "basic",
            "secret": "{chatbot_login_name}:{chatebot_login_passwd}"
        }
    ]
}
```

> Replace `{chatbot_login_name}` and `{chatebot_login_passwd}` with the chatbot’s login account name and password in the Tinode server.

Use the following command to start the chatbot:

    python -m Karuha ./config.json

Now you can view the messages others have sent to the chatbot from the command line.

## User Interaction

Of course, only receiving messages is not enough, we need some interaction with users. Karuha provides a powerful command system. With the command system, we can conveniently receive user-issued information and make appropriate responses.

### Simple Command Example
Let's start with a very simple command. We want to implement a hi command, which replies Hello! when the chatbot receives this command.

Create a new file hi.py and write the following:

```python
from karuha import on_command, MessageSession

@on_command
async def hi(session: MessageSession) -> None:
    await session.send("Hello!")
```

The above code involves some Python knowledge, I will briefly introduce it one by one. If you already know this knowledge, you can skip this part.

In the first line of code, we import the `on_command` decorator and `MessageSession` class from the `karuha` module. A decorator is an object that can be used to decorate a function or class. Here, its usage is as shown in the fourth line, where the function is modified with `@on_command` before the function definition. The modified function will be registered as a command and will be called when the corresponding message is received.

Next is the definition of the `hi` function. Here we use `async def` to define the command function. Unlike ordinary functions defined using `def`, functions defined with `async def` are asynchronous functions. Asynchronous is a relatively complex topic. It doesn't matter if you don't understand it. Here we will only use some simple syntax similar to normal functions.

You may be unfamiliar with the line `(session: MessageSession) -> None`. This is a type annotation that describes the parameter types and return value types of a function. Here we declare that the type of `session` is `MessageSession`, and the return value type is `None`, that is, there is no return value. In Python, type annotations are optional, but for commands in Karuha, they are used for parsing message data. Although not required, it is recommended to add type annotations when writing commands so that Karuha can better understand your code.

Then there is the content of the function, which is very short and only one line. `session` is a session object, which encapsulates many APIs for receiving and sending messages. Here, we use the `send` method to send the message. `send` is an asynchronous method, so you need to use `await` in front when calling it.

After finishing writing the command, we can run the chatbot to test it. Run the chatbot using the following command:

```sh
python -m Karuha ./config.json -m hi
```

Then in the conversation with the bot, enter the following:

     /hi


> By default, karuha will only process text messages starting with `/` as commands. This behavior can be set through the `set_prefix` function before defining all commands.

If everything goes well, you should see the 'Hello!' reply from the bot.

### Getting User Input

In the above example, we did not directly use the user's input. What if I want to get the user's input content?

One way is to use the message record in the `session`. `session.last_message` contains the complete user input. But this is not very elegant.

A more convenient method is to directly modify the function signature, such as:

```python
async def hi(session: MessageSession, text: str) -> None:
    ...
```

We add a text parameter of type str to represent the user's input content. Let's modify the contents of the hi function a bit to allow it to:


```python
@on_command
async def hi(session: MessageSession, text: str) -> None:
    total = text.split(' ', 1)
    if len(total) == 1:
        await session.send("Hello!")
    name = total[1]
    await session.send(f"Hello {name}!")
```

The code above builds on the previous logic by adding the name to greet in the command's response. This involves some string processing operations that are not explained here for now.

Run the chatbot and send it:

    /hi world

You should receive the chatbot's response of `Hello world!`.

## About More
Of course, Karuha provides more APIs than just these. If you are interested in learning more, please refer to the source code of the library.

### Development Goals
Features that may be added in the future include:

- [ ] APIs related to user information getting and setting
- [ ] Automatic argument parsing in argparse format for commands

### Architecture Overview
The overall architecture of Karuha is as follows:

| Layer | Provided Module | Function |
| --- | --- | --- |
| Upper layer | karuha.command | 命Command registration and processing |
| Middle layer | karuha.event | Async event-driven system |
| Lower layer | karuha.bot | Tinode API basic encapsulation |

In addition, there are some relatively independent modules:

| Module | Function |
| --- | --- |
| karuha.text | Text processing module |
| karuha.config | Configuration file parsing module |
| karuha.plugin_server | Plugin module for Tinode server, not enabled by default |

### Message Handling
Karuha internally provides two complementary message handling systems: the asynchronous event message system (event) and the message dispatcher system (dispatcher).

The asynchronous event message is used to receive and parallelly process messages. By registering message event handlers, the related information of the message can be quickly collected. Message handlers are parallel and non-interfering with each other.

The message dispatcher is downstream of the asynchronous event message system. It is used to determine the final message handler. This system is used to handle the connection between the middle layer event system and the upper command system. If you want to provide feedback to users according to message content and avoid interference from other message processing modules, you should use this system.

## About Documentation
This project does not have documentation plans. Documentation will not be provided for the foreseeable future. If you want to provide documentation for this project, I will greatly appreciate it.

## About Contribution
Welcome to post your questions and suggestions in issues. If you are interested in developing Tinode chatbots, welcome to contribute.
