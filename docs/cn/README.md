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

在开始前，你需要确保：

1. 已经安装了Karuha框架即其所需要的包
2. 在本地有运行的Tinode服务，其gRPC端口为默认值16060。如果你的服务不在本地，在接下来的代码中，你需要额外添加服务器的配置项
3. 最好具有一定的Python异步编程基础

Karuha框架基于异步的事件处理机制
