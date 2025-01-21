# Karuha

[![License](https://img.shields.io/github/license/Ovizro/Karuha.svg)](/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/KaruhaBot.svg)](https://pypi.python.org/pypi/KaruhaBot)
[![Build Status](https://github.com/Ovizro/Karuha/actions/workflows/test_cov.yml/badge.svg)](https://github.com/Ovizro/Karuha/actions)
![PyPI - Downloads](https://img.shields.io/pypi/dw/KaruhaBot)
![Python Version](https://img.shields.io/badge/python-3.8%20|%203.9%20|%203.10%20|%203.11%20|%203.12-blue.svg)

一个简单的Tinode聊天机器人框架

**语言: [English](README.md)/中文**

库的名称 `Karuha`来自游戏星空列车与白的旅行中的角色 狩叶·朗姆柯妮（カルハ・ラムコネ）

<div align="center">

![Karuha](/docs/img/tw_icon-karuha2.png)

</div>

> カルハ・ラムコネと申します。カルハちゃんって呼んでいいわよ

## 安装

从Pypi安装：

    pip install KaruhaBot

或从源码安装：

    git clone https://github.com/Visecy/Karuha.git
    cd Karuha
    make install

## 快速开始

在开始前，你需要确保在本地有运行的Tinode服务，其gRPC端口为默认值16060。

> 如果你的服务不在本地或更改了gRPC端口，在接下来的代码中，你可能需要修改或额外添加服务器的配置项。

创建一个新的文件 `config.json`并写入以下内容作为配置文件：

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

> 将 `{chatbot_login_name}` 和 `{chatebot_login_passwd}` 替换为聊天机器人在 Tinode 服务器中的登录帐户名和密码。

使用以下的命令启动聊天机器人：

    python -m Karuha ./config.json

现在就可以在命令行上查看其他人发给聊天机器人的消息了。

## 用户交互

只能接收消息当然是不够的，我们需要与用户进行一些交互。Karuha提供了一套强大的命令系统。利用命令系统，我们可以方便的接收用户发出的信息并进行相应的回复。

### 简单命令示例

让我们从一个最简单的命令开始。我们希望实现一个 `hi`命令，当机器人收到此命令时，回复 `Hello!`。

新建一个 `hi.py`，并在其中写入以下内容：

```python
from karuha import on_command, MessageSession


@on_command
async def hi(session: MessageSession) -> None:
    await session.send("Hello!")
```

以上的代码涉及到一些Python知识，我将会逐个的简单介绍一下。如果你已经了解这些知识，可以跳过这一部分。

代码的第一行，我们从 `karuha`模块中导入了 `on_command`装饰器和 `MessageSession`类。装饰器是一种可以用来修饰函数或类的的对象。在这里，它的用法如第四行所示，在函数定义前通过 `@on_command`来修饰函数。被修饰的函数会被注册为命令，将会在收到对应的消息时被调用。

接下来是 `hi`函数的定义。这里我们使用 `async def`来定义命令函数。与使用 `def`定义的普通函数不同，`async def`定义的函数是异步函数。异步是一个比较复杂的话题，如果你不了解它也没有关系，这里我们只会使用一些简单的与正常函数类似的语法。

你可能对 `(session: MessageSession) -> None`这一行有些陌生。这是一段类型注释，用于说明函数的参数类型和返回值类型。这里我们声明了 `session`的类型为 `MessageSession`，而返回值类型为 `None`，也就是没有返回值。在Python中，类型注释是可选的，但对于Karuha中的命令来说，它们会被用于消息数据的解析。虽然不是必须的，但建议在编写命令时添加类型注释，以便于Karuha更好的理解你的代码。

然后是函数的内容，这里非常短只有一行。`session`是一个会话对象，其中封装了很多接收与发送消息的API。在这里，我们使用 `send`方法来发送消息。`send`是一个异步方法，因此在调用时需要在前面使用 `await`。

在完成编写命令后，我们可以来运行一下机器人来测试一下。使用如下的命令运行机器人：

```sh
python -m karuha ./config.json -m hi
```

然后在与机器人的对话中，输入以下内容：

    /hi

> 在默认情况下，karuha只会将以 `/`为开头的文本消息作为命令处理，此行为可以在定义所以命令前通过 `set_prefix`函数来设置。

如果一切顺利，你就应该能看到机器人回复的 `Hello!`了。

### 示例扩展

在上面的示例中，我们并没有直接用到用户的输入内容。如果我希望获取用户的输入内容应该怎么办呢？

一个方法是使用 `session`中的消息记录。`session.last_message`中就包含了完整的用户输入内容。但这样并不够雅观。

更加方便的方法是直接修改函数签名，比如：

```python
from typing import List

@on_command
async def hi(session: MessageSession, argv: List[str]) -> None:
    ...
```

我们增加了一个 `argv`参数，类型为 `List[str]`，表示用户输入的内容。让我们稍微修改一下 `hi`函数的内容：

```python
@on_command
async def hi(session: MessageSession, argv: List[str]) -> None:
    if nor argv:
        await session.send("Hello!")
        return
    name = argv[0]
    await session.send(f"Hello {name}!")
```

以上代码中，我们在之前的逻辑的基础上，在命令的回复内容中增加要打招呼的名称。

让我们运行机器人，然后向它发送以下内容试试：

    /hi world

你就会收到机器人返回的 `Hello world!`了。

## 关于更多

当然Karuha提供的API并不止这些，如果你想对更多内容感兴趣，可以参考库的源码。

### 特性与支持

目前已经实现的功能如下：

- [X] 命令系统
- [X] 富文本（Drafty）解析
- [X] 基于规则匹配的聊天消息处理
- [X] 用户及话题信息读取✨
- [X] 代理发送机器人✨
- [X] Tinode插件服务器✨
- [X] 客户端低层级API封装
  - [X] `hi`消息
  - [X] `acc`消息
  - [X] `login`消息
  - [X] `sub`消息
  - [X] `leave`消息
  - [X] `pub`消息
  - [X] `get`消息
  - [X] `set`消息
  - [X] `del`消息
  - [X] `note`消息
- [X] 服务端低层级API处理
  - [X] `data`消息
  - [X] `ctrl`消息
  - [X] `meta`消息
  - [X] `pres`消息
  - [X] `info`消息
- [X] 大文件上传下载✨

> 带有✨标记的项是实验性的功能，其功能可能会存在问题，需要进一步的实验和反馈，这些功能的接口也可能会在未来发生破坏性更改。

在接下来可能会添加的功能包括：

- [ ] 用户及话题信息修改
- [ ] 音频附件上传支持
- [ ] 视频附件上传支持
- [ ] 基于http及websocket的底层API封装
- [ ] argparse格式的命令参数自动解析
- [ ] 使用sqlalchemy重构store模块

### 模块开发

目前，karuha对模块开发的支持较为简单。没有专门用于聊天机器人模块定义的API，但如果只是预设一些命令还是可以支持的。

在外部模块定义命令的方式与正常的定义方式类似。但为了避免影响用户的相关命令设置，我们需要新建一个命令集合(CommandCollection)。建立命令集合并在其中定义命令的方法如下：

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

> 注意，为了使命令集合生效，需要调用 `add_sub_collection`函数将命令集合添加到子命令集合中。

### 架构说明

Karuha的总体架构如下：

| 接口层次 | 提供模块       | 功能               |
| -------- | -------------- | ------------------ |
| 上层     | karuha.command | 命令注册与处理     |
| 中层     | karuha.event   | 异步事件驱动系统   |
| 底层     | karuha.bot     | Tinode API基础封装 |

除此之外，也有一些较为独立的模块：

| 模块                 | 功能                                   |
| -------------------- | -------------------------------------- |
| karuha.text          | 文本处理模块                           |
| karuha.config        | 配置文件解析模块                       |
| karuha.plugin_server | Tinode服务器使用的插件模块，默认不启用 |

### 消息处理

karuha内部提供了两相互配合的消息处理系统，即异步消息事件系统（event）和消息调度器系统（dispatcher）。

异步消息事件用于接收并并行的处理消息。通过注册消息事件处理器，可以快速的收集到消息的相关信息。不同的消息处理器间是并行且互不干扰的。

消息调度器则位于异步消息事件系统的下游，用于决定最终的消息的处理者。此系统用来承接中层事件系统与上层的命令系统。如果你希望根据消息内容对用户进行反馈并避免被其他消息处理模块干扰，则应该使用此系统。

## 关于文档

此项目并没有完善文档的计划。在可预见的时间内，此项目都不会有文档。如果你希望为此项目提供文档，我将感激不尽。

## 关于贡献

欢迎在issues中提出你的问题和建议。如果你对Tinode聊天机器人的开发感兴趣，欢迎参与贡献。
