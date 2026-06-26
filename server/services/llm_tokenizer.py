# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""LLM 分词器——通过 DeepSeek API 按语义上下文分词，识别专有名词。

用法:
    from server.services.llm_tokenizer import tokenize
    tokens = tokenize("我在北京工作")  # → ['我', '在', '北京', '工作']
"""
import json
import logging
from openai import OpenAI

from server.config import config

logger = logging.getLogger(__name__)

_client: OpenAI | None = None

_SYSTEM_PROMPT = """# 切词系统提示词

## 角色定义

你是一个专业的文本切词专家。你的任务是将输入的文本根据语义上下文进行切分，
识别出有意义的词语单元。

## 输出要求

1. 根据上下文语义进行切词
2. 识别专有名词（如变量名、函数名、人名、项目特定术语等）
3. 识别出的专有名词需要单独标注

## 输出格式

```json
["词语1", "词语2", ..., "专有名词1", "专有名词2", ...]
```

## 专有名词识别

专有名词包括但不限于：
- 变量名、函数名、类名
- 项目名称、产品名称
- 人名、地名
- 技术术语、行业专有名词

## 注意事项

- 切词结果用于 BM25 关键词检索"""


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
        )
    return _client


def tokenize(text: str) -> list[str]:
    """使用 LLM 对文本进行语义分词。

    Args:
        text: 待分词文本

    Returns:
        分词结果列表；失败时返回空列表
    """
    client = _get_client()
    try:
        response = client.chat.completions.create(
            model=config.LLM_TOKENIZER_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        raw = response.choices[0].message.content
        # 清理 markdown 代码块标记
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:]
        tokens = json.loads(raw)
        if isinstance(tokens, list) and all(isinstance(t, str) for t in tokens):
            return tokens
        logger.warning("LLM 分词返回格式异常: %s", raw)
        return []
    except Exception as e:
        logger.warning("LLM 分词失败: %s", e)
        return []
