# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""角色剧情提取——从小说全文中逐角色提取专属剧情段落。"""

import asyncio
import json
import logging
import re

from server.config import config
from server.prompt_loader import get_prompt
from server.ai.common.llm_client import LLMClient

logger = logging.getLogger(__name__)

_llm = LLMClient(config)


def _safe_parse_json(raw: str) -> dict:
    """尽量宽容地解析 LLM 返回的 JSON，处理常见格式问题。"""
    if not raw or not raw.strip():
        return {}

    def _try_load(text: str) -> dict | None:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    candidates: list[str] = []

    candidates.append(raw.strip())

    stripped = raw.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline:].strip()
    if stripped.endswith("```"):
        stripped = stripped[:-3].strip()
    candidates.append(stripped)

    brace_start = stripped.find("{")
    brace_end = stripped.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        candidates.append(stripped[brace_start:brace_end + 1])

    fixed_candidates = []
    for c in candidates:
        fixed = re.sub(r",\s*([}\]])", r"\1", c)
        fixed_candidates.append(fixed)
    candidates.extend(fixed_candidates)

    seen = set()
    unique = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)

    for i, c in enumerate(unique):
        result = _try_load(c)
        if result is not None:
            if i > 0:
                logger.info("Extract JSON 通过策略 %d 成功解析", i)
            return result

    logger.warning("Extract JSON 解析失败（尝试了 %d 种策略）, raw=%.300s...", len(unique), raw)
    return {}


async def _extract_one_character(
    novel_full_text: str,
    character_profile: dict,
    system_prompt: str,
) -> tuple[str, str]:
    """为单个角色提取剧情上下文。

    Returns:
        (character_name, story_context)
    """
    char_name = character_profile.get("character_name", "未知角色")

    user_message = (
        f"## 小说全文\n\n{novel_full_text}\n\n"
        f"## 当前角色\n\n{json.dumps(character_profile, ensure_ascii=False, indent=2)}"
    )

    try:
        response = await _llm.generate(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            model=config.CHAT_MODEL,
            reasoning_effort=config.CHAT_REASONING_EFFORT,
            temperature=0.3,
            response_format={"type": "json_object"},
            caller="Extract",
        )
    except Exception as e:
        logger.error("extract_character_plots LLM 调用失败 [%s]: %s", char_name, e)
        return (char_name, "")

    if not response.content:
        logger.warning("extract_character_plots: LLM 返回空内容 [%s]", char_name)
        return (char_name, "")

    result = _safe_parse_json(response.content)
    if not result:
        logger.warning("首次 JSON 解析失败 [%s]，在同一上下文中让 LLM 修复格式", char_name)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": response.content},
            {"role": "user", "content": "你刚才输出的 JSON 格式有误，无法解析。请检查并修复，确保输出合法的 JSON。"},
        ]
        try:
            fix_response = await _llm.generate(
                messages=messages,
                model=config.CHAT_MODEL,
                reasoning_effort=config.CHAT_REASONING_EFFORT,
                temperature=0.3,
                response_format={"type": "json_object"},
                caller="Extract-Fix",
            )
            if fix_response.content:
                result = _safe_parse_json(fix_response.content)
                if result:
                    logger.info("JSON 修复重试成功（同上下文）[%s]", char_name)
                else:
                    logger.warning("JSON 修复重试仍失败 [%s]", char_name)
        except Exception as e:
            logger.warning("JSON 修复重试异常 [%s]: %s", char_name, e)

    story_context = result.get("story_context", "") if result else ""
    logger.info("角色 '%s' story_context: %d 字", char_name, len(story_context))
    return (char_name, story_context)


async def extract_character_plots(
    novel_full_text: str,
    characters: list[dict],
) -> dict[str, str]:
    """从小说全文中逐角色提取专属剧情段落（每个角色独立调用 LLM）。

    Args:
        novel_full_text: 小说全文文本。
        characters: 角色列表，每个 dict 至少包含 character_name/name 字段。

    Returns:
        {character_name: 该角色的剧情段落文本}。
    """
    if not novel_full_text or not characters:
        logger.warning("extract_character_plots: 小说文本或角色列表为空")
        return {c.get("character_name", c.get("name", "")): "" for c in characters}

    system_prompt = get_prompt("extract_llm/extract_system")
    if not system_prompt:
        logger.error("extract_character_plots: 无法加载系统提示词")
        return {c.get("character_name", c.get("name", "")): "" for c in characters}

    char_profiles = []
    for c in characters:
        profile = {
            "character_name": c.get("character_name", c.get("name", "未知角色")),
            "identity": c.get("identity", "未知"),
            "personality": c.get("personality", "未知"),
            "goal": c.get("goal", "未知"),
            "backstory": c.get("backstory", "未知"),
        }
        char_profiles.append(profile)

    logger.info("逐角色提取剧情: %d 个角色, 小说全文 %d 字符", len(characters), len(novel_full_text))

    # 并发调用，每个角色一次独立的 LLM 请求
    tasks = [
        _extract_one_character(novel_full_text, profile, system_prompt)
        for profile in char_profiles
    ]
    results = await asyncio.gather(*tasks)

    output: dict[str, str] = {}
    for name, context in results:
        output[name] = context

    logger.info("提取完成: %d 个角色剧情已生成", len(output))
    return output
