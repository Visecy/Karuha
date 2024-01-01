# Karuha

[![License](https://img.shields.io/github/license/Ovizro/Karuha.svg)](/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/KaruhaBot.svg)](https://pypi.python.org/pypi/KaruhaBot)
![Python Version](https://img.shields.io/badge/python-3.8%20|%203.9%20|%203.10%20|%203.11-blue.svg)

一个简单的Tinode聊天机器人框架

> 目前项目仍处于开发期，部分次要接口可能会频繁变化，造成的不便敬请谅解

库的名称`Karuha`来自游戏星空列车与白的旅行中的角色 狩叶·朗姆柯妮（カルハ・ラムコネ）

<center>

![Karuha](/docs/img/tw_icon-karuha2.png)

</center>

> カルハ・ラムコネと申します。カルハちゃんって呼んでいいわよ

# 安装

从Pypi安装：

    pip install KaruhaBot

或从源码安装：

    git clone https://github.com/Ovizro/Karuha.git
    cd Karuha
    make install

# 快速开始

在开始前，你需要确保在本地有运行的Tinode服务，其gRPC端口为默认值16060。如果你的服务不在本地，在接下来的代码中，你需要额外添加服务器的配置项。

创建一个新的文件`config.json`并写入以下内容作为配置文件：

```json
{
    "server": {
        "host": "localhost:16060",
        "listen": "0.0.0.0:40051"
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

> 将 `{chatbot_login_name}` 和 `{chatebot_login_passwd}` 替换为聊天机器人在 Tinode 服务器中的登录帐户名和密码。

使用以下的命令启动聊天机器人：

    python -m Karuha ./config.json

现在您可以在命令行上查看其他人发送到聊天机器人的消息。是的，这就是我们目前能做到的大部分内容。

## 更进一步？

好吧，其实我们的确可以再进一步，让我们试着回复一些消息吧。

至于为什么我并不在上面一段提及这个，因为就目前来说，回复消息的确不是几件简单的事情。这需要我们手动对事件进行绑定。但不要担心，我们很快就会有一套命令模块来简化这一流程。

由于这涉及到低层级API，故此处仅提供一个例子，以展示其目前在Python中的使用方法：

```python
import karuha
from karuha import Bot, MessageEvent, PublishEvent


bot = Bot(
    "chatbot",
    "basic",
    "chatbot:123456"
)


@karuha.on(MessageEvent)
async def reply(event: MessageEvent) -> None:
    if event.text == "Hello!":
        await event.bot.publish(event.topic, "Hello world!")


if __name__ == "__main__":
    karuha.init_config()
    karuha.add_bot(bot)
    karuha.run()
```
