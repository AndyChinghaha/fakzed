"""Real-API smoke test against DeepSeek.

Reads the key from the DEEPSEEK_API_KEY environment variable (never hardcoded).

    $env:DEEPSEEK_API_KEY="..." ; python scripts/smoke_deepseek.py
"""

import os
import sys

from pydantic import BaseModel

from fakzed import Agent, Message, create_model, tool


def section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def main() -> int:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        print("Set DEEPSEEK_API_KEY first.", file=sys.stderr)
        return 1

    # 1. factory + adapter wiring -------------------------------------------
    section("1. create_model 工厂解析")
    model = create_model("deepseek:deepseek-chat", api_key=key)
    print("class:", type(model).__name__)
    print("provider:", model.provider, "| base_url:", model.base_url)

    # 2. basic chat -----------------------------------------------------------
    section("2. 基本对话")
    resp = model.response(messages=[Message(role="user", content="用一句话介绍你自己")])
    print("content:", resp.content)
    print("usage:", resp.usage)

    # 3. streaming ------------------------------------------------------------
    section("3. 流式输出")
    print("stream:", end=" ")
    for event in model.response_stream(messages=[Message(role="user", content="从 1 数到 5")]):
        if event.event == "chunk" and event.content:
            print(event.content, end="", flush=True)
    print()

    # 4. tool calling ---------------------------------------------------------
    section("4. 工具调用（模型主动调用）")

    @tool
    def get_weather(city: str) -> str:
        """Return the current weather of a city."""
        return f"{city}: 晴, 22°C（模拟数据）"

    resp = model.response(
        messages=[Message(role="user", content="北京今天天气怎么样？")],
        tools=[get_weather.to_model_tool()],
    )
    print("tool_calls:", resp.tool_calls)
    print("content:", resp.content or "(empty)")

    # 5. structured output -----------------------------------------------------
    section("5. 结构化输出")

    class CityInfo(BaseModel):
        city: str
        population_millions: float
        landmark: str

    resp = model.response(
        messages=[
            Message(
                role="user",
                content="介绍北京：城市名、人口（百万）、一个地标。直接输出 JSON 对象。",
            )
        ],
        response_format=CityInfo,
    )
    print("raw content:", resp.content)
    print("parsed:", resp.parsed)
    assert isinstance(resp.parsed, CityInfo), "parsed should be a CityInfo instance"

    # 6. agent end-to-end (real multi-turn tool loop) ---------------------------
    section("6. Agent 端到端（真实工具循环 + 流式）")

    agent = Agent(
        name="weather assistant",
        description="answers weather questions",
        model="deepseek:deepseek-chat",
        tools=[get_weather],
    )
    agent.print_response("上海今天天气怎么样？", stream=True)

    print("\nAll smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
