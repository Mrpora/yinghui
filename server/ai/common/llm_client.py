# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""统一 LLM 客户端——全局唯一调用入口。

特性：
- 思考模式写死开启（extra_body={"thinking": {"type": "enabled"}}）
- 内置可重试错误自动重试（最多 config.LLM_RETRY_MAX 次，退避 2s/4s/8s…）
- 返回 ChatResponse 数据类（content / reasoning_content / tool_calls / usage）
- 支持 response_format 参数（用于 completer/extract 的 JSON 结构化输出）
- 不负责 context 维护——messages.append 由各 Agent 自行完成
"""
import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ChatResponse:
    content: str | None = None
    reasoning_content: str | None = None
    tool_calls: list[dict] = field(default_factory=list)
    usage: Usage | None = None


class LLMClient:
    """OpenAI 兼容 LLM 客户端，思考模式写死开启。"""

    def __init__(self, config):
        from openai import AsyncOpenAI
        self.config = config
        self._client = AsyncOpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
        )

    async def generate(
        self,
        messages: list[dict],
        *,
        reasoning_effort: str,
        model: str | None = None,
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        stop: list[str] | None = None,
        seed: int | None = None,
        response_format: dict | None = None,
        caller: str = "",
    ) -> ChatResponse:
        """发送请求到 LLM，内置可重试错误自动重试。

        Args:
            messages: 对话消息列表
            reasoning_effort: 推理强度（max/high/medium/low/minimal/none）
            model: 模型名，默认用 config.CHAT_MODEL
            tools: 工具定义列表
            max_tokens: 最大输出 token 数
            temperature: 采样温度
            top_p: 核采样
            frequency_penalty: 频率惩罚
            presence_penalty: 存在惩罚
            stop: 停止序列
            seed: 随机种子
            response_format: 响应格式（如 {"type": "json_object"}）

        Returns:
            ChatResponse 包含 content / reasoning_content / tool_calls / usage

        Raises:
            最后一次重试的异常（重试耗尽时）
        """
        import openai

        max_retries = self.config.LLM_RETRY_MAX
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                kwargs: dict = {
                    "model": model or self.config.CHAT_MODEL,
                    "messages": messages,
                    "reasoning_effort": reasoning_effort,
                    "extra_body": {"thinking": {"type": "enabled"}},
                }
                if tools:
                    kwargs["tools"] = tools
                if max_tokens is not None:
                    kwargs["max_tokens"] = max_tokens
                if temperature is not None:
                    kwargs["temperature"] = temperature
                if top_p is not None:
                    kwargs["top_p"] = top_p
                if frequency_penalty is not None:
                    kwargs["frequency_penalty"] = frequency_penalty
                if presence_penalty is not None:
                    kwargs["presence_penalty"] = presence_penalty
                if stop is not None:
                    kwargs["stop"] = stop
                if seed is not None:
                    kwargs["seed"] = seed
                if response_format is not None:
                    kwargs["response_format"] = response_format

                logger.info(
                    "🤖 LLM 调用 model=%s messages=%d tools=%s attempt=%d/%d",
                    kwargs["model"], len(messages),
                    [t["function"]["name"] for t in tools] if tools else [],
                    attempt + 1, max_retries + 1,
                )

                response = await self._client.chat.completions.create(**kwargs)
                choice = response.choices[0].message

                usage = None
                if hasattr(response, 'usage') and response.usage:
                    usage = Usage(
                        prompt_tokens=response.usage.prompt_tokens or 0,
                        completion_tokens=response.usage.completion_tokens or 0,
                        total_tokens=response.usage.total_tokens or 0,
                    )

                tag = f"[{caller}] " if caller else ""
                logger.info("%s💰 本次调用消耗 %d tokens", tag, usage.total_tokens if usage else 0)

                return ChatResponse(
                    content=choice.content,
                    reasoning_content=getattr(choice, "reasoning_content", None),
                    tool_calls=[
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in (choice.tool_calls or [])
                    ],
                    usage=usage,
                )

            except (openai.RateLimitError, openai.APITimeoutError,
                    openai.APIConnectionError, openai.InternalServerError) as e:
                last_exception = e
                if attempt < max_retries:
                    wait = 2 ** attempt * 2  # 2s, 4s, 8s...
                    logger.warning(
                        "LLM 调用失败（第 %d/%d 次），%ds 后重试: %s",
                        attempt + 1, max_retries + 1, wait, e,
                    )
                    await asyncio.sleep(wait)
            except (openai.BadRequestError, openai.AuthenticationError) as e:
                logger.error("LLM 调用因不可重试错误而失败: %s", e)
                raise
            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    wait = 2 ** attempt * 2
                    logger.warning(
                        "LLM 调用失败（第 %d/%d 次），%ds 后重试: %s",
                        attempt + 1, max_retries + 1, wait, e,
                    )
                    await asyncio.sleep(wait)

        logger.error("LLM 调用耗尽全部 %d 次尝试", max_retries + 1)
        raise last_exception
