# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""世界配置智能补全——一键补全不完整的世界设定。"""

import json
import logging
import re

from server.config import config
from server.prompt_loader import get_prompt
from server.ai.common.llm_client import LLMClient

logger = logging.getLogger(__name__)

_llm = LLMClient(config)


def _safe_parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        first_newline = raw.find("\n")
        if first_newline != -1:
            raw = raw[first_newline:].strip()
    if raw.endswith("```"):
        raw = raw[:-3].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        logger.warning("Completer JSON 解析失败, raw=%.300s...", raw)
        return {}


def _build_user_prompt(world_data: dict, character_count: int) -> str:
    parts = []
    world_name = world_data.get("name", "") or world_data.get("world_name", "")
    world_description = world_data.get("description", "") or world_data.get("world_description", "")
    parts.append(f"世界名称：{world_name}")
    parts.append(f"世界描述：{world_description}")

    world_history = world_data.get("world_history", "")
    if world_history:
        parts.append(f"\n已有世界历史（保留）：\n{world_history}")

    rules = world_data.get("rules", [])
    if rules:
        parts.append("\n已有规则（保留）：")
        for i, r in enumerate(rules, 1):
            parts.append(f"  {i}. {r}")
    else:
        parts.append("\n请生成 3 条世界规则。")

    initial_event = world_data.get("initial_event")
    if initial_event and (initial_event.get("content") if isinstance(initial_event, dict) else False):
        parts.append("\n已有初始事件（保留）：")
        parts.append(f"  时间：{initial_event.get('time', '未填写')}")
        parts.append(f"  内容：{initial_event['content']}")
    else:
        parts.append("\n请生成初始事件（含时间）。")

    characters = world_data.get("characters", [])
    if characters:
        parts.append(f"\n已有 {len(characters)} 个角色（保留）：")
        for c in characters:
            parts.append(f"  - {c.get('name', '?')}（{c.get('identity', '?')}）")
        if len(characters) < character_count:
            parts.append(f"请再生成 {character_count - len(characters)} 个角色，补至 {character_count} 人。")
        else:
            parts.append(f"角色数量已满足 {character_count} 人要求，请补全缺失属性（如 backstory、attitudes 等）。")
        parts.append("每个角色 identity 格式：性别，身份描述。")
    else:
        parts.append(f"\n请生成 {character_count} 个角色。")
        parts.append("每个角色 identity 格式：性别，身份描述。")

    if world_history:
        parts.append("\n请生成每个角色的背景故事（150-300字）。")
    else:
        parts.append("\n请生成世界历史（200-500字）和每个角色的背景故事（150-300字）。")

    return "\n".join(parts)


async def smart_complete_world(
    world_data: dict,
    character_count: int = 2,
) -> dict:
    """调用 LLM 一键补全世界配置。

    Args:
        world_data: 不完整的世界配置。
        character_count: 期望角色数量。

    Returns:
        补全后的世界配置：{world_history, rules, initial_event, characters}。
    """
    system_prompt = get_prompt("completer_llm/completer_system")
    if not system_prompt:
        logger.error("smart_complete_world: 无法加载系统提示词")
        return {
            "world_history": world_data.get("world_history", ""),
            "rules": world_data.get("rules", [])[:3],
            "initial_event": world_data.get("initial_event"),
            "characters": world_data.get("characters", [])[:character_count],
        }

    user_prompt = _build_user_prompt(world_data, character_count)
    world_name = world_data.get("name", "") or world_data.get("world_name", "")
    logger.info("世界补全请求 name=%s character_count=%d", world_name, character_count)

    try:
        response = await _llm.generate(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=config.EVOLUTION_DIRECTOR_MODEL,
            reasoning_effort=config.EVOLUTION_DIRECTOR_REASONING_EFFORT,
            temperature=0.8,
            response_format={"type": "json_object"},
            caller="Completer",
        )
    except Exception as e:
        logger.error("smart_complete_world LLM 调用失败: %s", e)
        return {
            "world_history": world_data.get("world_history", ""),
            "rules": world_data.get("rules", [])[:3],
            "initial_event": world_data.get("initial_event"),
            "characters": world_data.get("characters", [])[:character_count],
        }

    if not response.content:
        logger.error("smart_complete_world: LLM 无响应")
        return {
            "world_history": world_data.get("world_history", ""),
            "rules": world_data.get("rules", [])[:3],
            "initial_event": world_data.get("initial_event"),
            "characters": world_data.get("characters", [])[:character_count],
        }

    result = _safe_parse_json(response.content)
    return {
        "world_history": result.get("world_history", world_data.get("world_history", "")),
        "rules": result.get("rules", [])[:3],
        "initial_event": result.get("initial_event", world_data.get("initial_event")),
        "characters": result.get("characters", [])[:character_count],
    }
