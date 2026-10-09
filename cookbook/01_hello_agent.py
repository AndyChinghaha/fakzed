"""Cookbook 01: your first Agent — hello world, four run paths.

Run:  python cookbook/01_hello_agent.py
Real provider: replace `scripted(...)` with "deepseek:deepseek-chat".
"""

import asyncio

from _cookbook_utils import scripted

from fakzed import Agent

# The model answers are scripted so this example needs no API key.
model = scripted(
    "你好！我是 fakzed 助手，用一句话介绍自己：我是一个轻量级 Agent 框架。",
    "好的，再说一遍：我是轻量级 Agent 框架。",
    "你好！",
    "不客气，随时找我。",
)

agent = Agent(
    name="hello-bot",
    model=model,
    instructions="你是一个简洁的中文助手。",
)

# ① synchronous run
resp = agent.run("用一句话介绍你自己")
print("1) run        :", resp.content)
print("   session_id :", agent.session_id)

# ② streaming run (sync generator)
print("2) run_stream :", end=" ")
for chunk in agent.run_stream("再说一遍"):
    print(chunk.content, end="")
print()

# ③ async run


async def async_demo() -> None:
    resp = await agent.arun("你好")
    print("3) arun       :", resp.content)

    print("4) arun_stream:", end=" ")
    async for chunk in agent.arun_stream("谢谢"):
        print(chunk.content, end="")
    print()


asyncio.run(async_demo())
