"""
测试脚本：使用 LangChain Agent 实现图片理解（Vision）

通过 Dashscope OpenAI 兼容接口调用 qwen-vl 多模态模型，
仅支持公开可访问的图片 URL。

用法:
  cd backend
  uv run python scripts/test_vision_agent.py <图片URL>
  uv run python scripts/test_vision_agent.py https://example.com/image.jpg
  uv run python scripts/test_vision_agent.py https://example.com/image.jpg --simple
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI


# ---------------------------------------------------------------------------
# 工具定义
# ---------------------------------------------------------------------------

@tool
def describe_image_detail(image_url: str, focus: str = "全面描述") -> str:
    """对图片进行详细描述。

    Args:
        image_url: 图片公开 URL
        focus: 描述重点，如 "颜色分析"、"文字识别"、"场景描述" 等
    """
    return f"已对图片进行详细分析，重点关注: {focus}。请根据你的视觉理解直接输出分析结果。"


# ---------------------------------------------------------------------------
# 图片消息构建
# ---------------------------------------------------------------------------

def build_image_message(image_url: str, prompt: str) -> HumanMessage:
    """构建包含图片 URL 的 HumanMessage。"""
    if not image_url.startswith(("http://", "https://")):
        raise ValueError(f"请提供公开可访问的图片 URL (http/https)，当前输入: {image_url}")

    image_content = {
        "type": "image_url",
        "image_url": {"url": image_url},
    }

    return HumanMessage(content=[
        image_content,
        {"type": "text", "text": prompt},
    ])


# ---------------------------------------------------------------------------
# Agent 创建
# ---------------------------------------------------------------------------

def create_vision_agent() -> tuple:
    """创建图片理解 Agent，返回 (agent, model)。"""
    # 使用 Dashscope 的 qwen-vl-plus 多模态模型（OpenAI 兼容接口）
    api_key = os.getenv("EMBEDDING_API_KEY", "")
    base_url = os.getenv("EMBEDDING_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    vision_model = os.getenv("VISION_MODEL", "qwen3.5-flash")

    model = ChatOpenAI(
        model=vision_model,
        api_key=api_key,
        base_url=base_url,
        streaming=True,
        max_tokens=2048,
    )

    agent = create_agent(
        model=model,
    )

    return agent, model


# ---------------------------------------------------------------------------
# 运行
# ---------------------------------------------------------------------------

async def run_vision_agent(image_url: str, prompt: str | None = None):
    """运行图片理解 Agent。"""
    if prompt is None:
        prompt = (
            "请仔细观察这张图片，给出详细的描述，包括：\n"
            "1. 图片的主要内容\n"
            "2. 视觉元素（颜色、构图、风格）\n"
            "3. 如果有文字，请识别并列出\n"
            "4. 你的整体理解和评价"
        )

    agent, model = create_vision_agent()
    message = build_image_message(image_url, prompt)

    print(f"\n{'='*60}")
    print(f"  图片理解 Agent")
    print(f"  模型: {model.model_name}")
    print(f"  图片 URL: {image_url}")
    print(f"{'='*60}\n")

    # 流式输出
    print("📷 分析结果:\n")
    response_text = []

    async for event in agent.astream_events(
        {"messages": [message]},
        version="v2",
    ):
        kind = event.get("event")

        # 捕获 LLM 流式 token
        if kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content") and chunk.content:
                print(chunk.content, end="", flush=True)
                response_text.append(chunk.content)

        # 捕获工具调用
        elif kind == "on_tool_start":
            tool_name = event.get("name", "unknown")
            tool_input = event.get("data", {}).get("input", {})
            print(f"\n🔧 调用工具: {tool_name}")
            print(f"   参数: {tool_input}\n")

    print(f"\n\n{'='*60}")
    print("✅ 分析完成")
    print(f"{'='*60}\n")

    return "".join(response_text)


# ---------------------------------------------------------------------------
# 直接调用（不走 Agent，简单测试）
# ---------------------------------------------------------------------------

async def run_simple_vision(image_url: str, prompt: str | None = None):
    """直接调用视觉模型（不使用 Agent），用于快速验证模型可用性。"""
    if prompt is None:
        prompt = "请描述这张图片的内容。"

    api_key = os.getenv("EMBEDDING_API_KEY", "")
    base_url = os.getenv("EMBEDDING_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    vision_model = os.getenv("VISION_MODEL", "qwen-vl-plus")

    model = ChatOpenAI(
        model=vision_model,
        api_key=api_key,
        base_url=base_url,
        streaming=True,
        max_tokens=2048,
    )

    message = build_image_message(image_url, prompt)

    print(f"\n{'='*60}")
    print(f"  简单视觉模型调用 (非 Agent)")
    print(f"  模型: {vision_model}")
    print(f"{'='*60}\n")

    async for chunk in model.astream([message]):
        if chunk.content:
            print(chunk.content, end="", flush=True)

    print(f"\n\n{'='*60}")
    print("✅ 完成")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    load_dotenv()

    if len(sys.argv) < 2:
        print(__doc__)
        print("错误: 请提供图片 URL")
        print("\n示例:")
        print("  uv run python scripts/test_vision_agent.py https://example.com/image.jpg")
        print("  uv run python scripts/test_vision_agent.py https://example.com/image.jpg --simple")
        sys.exit(1)

    image_url = sys.argv[1]
    simple_mode = "--simple" in sys.argv

    if simple_mode:
        asyncio.run(run_simple_vision(image_url))
    else:
        asyncio.run(run_vision_agent(image_url))


if __name__ == "__main__":
    main()
