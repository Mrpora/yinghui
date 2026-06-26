# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""导演 Agent 工具集——导演 LLM 可调用的全部 function calling 工具。

工具：distribute_perceptions / query_interaction_stance / notify_actor /
      write_timeline_event / write_round_summary / push_branches /
      push_validation_result / update_relationships
"""

import asyncio
import json
import logging
import re

from server.config import config
from server.services.session_manager import Session
from server.ai.common.llm_client import LLMClient
from server.ai.evolution_agent.character_tools import CHARACTER_TOOLS, write_my_memory

logger = logging.getLogger(__name__)


def _sanitize_json_strings(raw: str) -> str:
    """转义 JSON 字符串值内的未转义控制字符（\\n \\r \\t）。"""
    result: list[str] = []
    in_string = False
    escaped = False
    for ch in raw:
        if escaped:
            result.append(ch)
            escaped = False
            continue
        if ch == '\\':
            result.append(ch)
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string:
            if ch == '\n':
                result.append('\\n')
            elif ch == '\r':
                result.append('\\r')
            elif ch == '\t':
                result.append('\\t')
            else:
                result.append(ch)
        else:
            result.append(ch)
    return ''.join(result)


def _safe_parse_json(raw: str, tool_name: str = "unknown") -> dict:
    """安全解析 LLM 返回的 JSON。"""
    sanitized = _sanitize_json_strings(raw)
    try:
        return json.loads(sanitized)
    except json.JSONDecodeError:
        pass

    fixed = sanitized.rstrip()
    open_braces = fixed.count("{") - fixed.count("}")
    open_brackets = fixed.count("[") - fixed.count("]")
    in_string = (fixed.count('"') - fixed.count('\\"')) % 2 != 0

    if in_string:
        fixed += '"'
    fixed += "]" * open_brackets
    fixed += "}" * open_braces

    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    logger.error("JSON 解析失败 tool=%s: %s...", tool_name, raw[:200])
    return {}


class DirectorTools:
    """导演 Agent 工具集——持有 LLMClient、SessionManager、SSEManager 引用。"""

    def __init__(self, llm_client: LLMClient, session_manager, sse_manager):
        self.llm = llm_client
        self.sessions = session_manager
        self.sse = sse_manager

    def _channel(self, session_id: str) -> str:
        return f"evolution:{session_id}"

    # ── distribute_perceptions ──

    async def distribute_perceptions(
        self, session: Session, perceptions: dict[str, str]
    ) -> dict:
        """将增量感知视图并行发送给所有角色，收集行动结果（不写入时间线）。"""
        char_names = [c for c in perceptions if c in session.character_contexts]
        logger.info("📡 感知派发 session=%s round=%d chars=%s",
                    session.id, session.current_round, char_names)

        async def _call_one(char_name: str, perception_text: str):
            result = await self._retry_with_fallback(
                lambda: self._call_character(session, char_name, perception_text, "回合行动")
            )
            return char_name, result

        results = {}
        tasks = [_call_one(cn, pt) for cn, pt in perceptions.items()
                 if cn in session.character_contexts]
        if tasks:
            gathered = await asyncio.gather(*tasks, return_exceptions=True)
            for item in gathered:
                if isinstance(item, Exception):
                    logger.error("角色调用异常 session=%s: %s", session.id, item)
                    continue
                cn, result = item
                results[cn] = result

        logger.info("📡 感知派发完成 session=%s chars=%d results=%d",
                    session.id, len(char_names), len(results))
        return results

    # ── _call_character ──

    async def _call_character(
        self, session: Session, char_name: str, perception: str, scene_label: str
    ) -> dict | None:
        """调用单个角色 LLM，注入感知视图，在写入记忆后产出行动。"""
        ctx = session.character_contexts[char_name]
        ctx.append({
            "role": "user",
            "content": f"[场景: {scene_label}]\n\n感知视图：\n{perception}",
        })

        accumulated = {"action": "", "motive": None, "inner_thoughts": None,
                       "conflict_self_assessment": None}
        max_loops = 5
        empty_retried = False

        for loop_idx in range(max_loops):
            try:
                resp = await self.llm.generate(
                    messages=ctx,
                    model=config.EVOLUTION_CHARACTER_MODEL,
                    tools=CHARACTER_TOOLS,
                    max_tokens=config.EVOLUTION_CHARACTER_MAX_TOKENS,
                    temperature=config.EVOLUTION_CHARACTER_ACTION_TEMPERATURE,
                    top_p=config.EVOLUTION_CHARACTER_ACTION_TOP_P,
                    frequency_penalty=config.EVOLUTION_CHARACTER_ACTION_FREQUENCY_PENALTY,
                    presence_penalty=config.EVOLUTION_CHARACTER_ACTION_PRESENCE_PENALTY,
                    caller="DirectorAgent-QueryStance",
                    reasoning_effort=config.EVOLUTION_CHARACTER_REASONING_EFFORT,
                )
            except Exception as e:
                logger.warning("角色 LLM 调用失败 char=%s: %s", char_name, e)
                return None

            # 空响应重试：模型偶发返回空内容且无工具调用，重试一次
            if not resp.tool_calls and not (resp.content or "").strip() and not empty_retried:
                reasoning = resp.reasoning_content or ""
                logger.warning(
                    "角色空响应 char=%s 将重试 reasoning=%s",
                    char_name, reasoning[-200:] if reasoning else "(无思考内容)",
                )
                empty_retried = True
                continue

            assistant_msg: dict = {"role": "assistant"}
            if resp.content is not None:
                assistant_msg["content"] = resp.content
            if resp.tool_calls:
                assistant_msg["tool_calls"] = resp.tool_calls
                if resp.reasoning_content:
                    assistant_msg["reasoning_content"] = resp.reasoning_content
            elif "content" not in assistant_msg:
                assistant_msg["content"] = ""
            ctx.append(assistant_msg)

            content = resp.content or ""
            if content:
                parsed = self._parse_character_output(content)
                if parsed["action"]:
                    accumulated["action"] = (
                        accumulated["action"] + "\n" + parsed["action"]
                        if accumulated["action"] else parsed["action"]
                    )
                for field in ("motive", "inner_thoughts", "conflict_self_assessment"):
                    if parsed.get(field) and not accumulated[field]:
                        accumulated[field] = parsed[field]

            if resp.tool_calls:
                memory_calls = []
                for tc in resp.tool_calls:
                    if tc["function"]["name"] == "write_my_memory":
                        try:
                            args = json.loads(tc["function"]["arguments"])
                        except json.JSONDecodeError:
                            args = {}
                        ctx.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps({"status": "success"}, ensure_ascii=False),
                        })
                        memory_calls.append(args)
                    else:
                        ctx.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps({
                                "status": "error",
                                "message": f"未知工具: {tc['function']['name']}",
                            }, ensure_ascii=False),
                        })
                for args in memory_calls:
                    await write_my_memory(
                        session, char_name,
                        type=args.get("type", "world_event"),
                        content=args.get("content", ""),
                        importance=args.get("importance", 5),
                    )
                continue

            if accumulated["action"]:
                return accumulated
            return self._parse_character_output(content)

        if accumulated["action"]:
            logger.warning("角色循环耗尽但有累积内容 char=%s", char_name)
            return accumulated
        logger.warning("角色循环耗尽 char=%s", char_name)
        return None

    @staticmethod
    def _parse_character_output(content: str) -> dict:
        """从角色输出中提取 action / motive / inner_thoughts / conflict_self_assessment。"""
        action = content
        motive = None
        inner_thoughts = None
        conflict_self_assessment = None

        motive_match = re.split(r'\*\*动机[：:]?\*\*', content, maxsplit=1)
        if len(motive_match) == 2:
            action = motive_match[0].strip()
            rest = motive_match[1]
            inner_match = re.split(r'\*\*内心活动[：:]?\*\*', rest, maxsplit=1)
            motive = inner_match[0].strip() or None
            if len(inner_match) == 2:
                rest2 = inner_match[1]
                conflict_match = re.split(r'\*\*冲突自评[：:]?\*\*', rest2, maxsplit=1)
                inner_thoughts = conflict_match[0].strip() or None
                if len(conflict_match) == 2:
                    conflict_self_assessment = conflict_match[1].strip() or None

        action = re.sub(r'^\s*\*\*行动(?:（续）)?[：:]?\*\*\s*', '', action)
        return {
            "action": action.strip() or content,
            "motive": motive,
            "inner_thoughts": inner_thoughts,
            "conflict_self_assessment": conflict_self_assessment,
        }

    async def _retry_with_fallback(self, factory) -> dict | None:
        try:
            return await factory()
        except Exception as e:
            logger.error("操作失败: %s", e)
            return None

    # ── query_interaction_stance ──

    async def query_interaction_stance(
        self, session: Session, perceptions: dict[str, str]
    ) -> dict[str, dict]:
        """询问所有角色互动参与意愿——并行询问各角色（上下文隔离，互不依赖）。"""
        logger.info("❓ 互动意愿询问 session=%s chars=%s",
                    session.id, list(perceptions.keys()))

        async def ask_one(name: str, perception_text: str) -> tuple[str, dict]:
            if name not in session.character_contexts:
                return name, {"stance": "不参与", "intervention_condition": None}
            stance = await self._call_stance(session, name, perception_text)
            return name, stance

        tasks = [ask_one(name, text) for name, text in perceptions.items()]
        results = {}
        for coro in asyncio.as_completed(tasks):
            name, stance = await coro
            results[name] = stance
        stances = {n: r.get("stance", "?") for n, r in results.items()}
        logger.info("❓ 互动意愿收集完成 session=%s stances=%s", session.id, stances)
        return results

    async def _call_stance(self, session: Session, char_name: str, perception: str) -> dict:
        ctx = session.character_contexts[char_name].copy()
        ctx.append({
            "role": "user",
            "content": f"[场景: 互动询问]\n\n感知视图：\n{perception}\n\n"
                       f"请输出你的参与意愿（参与 / 不参与 / 有条件）和介入条件（如有）。",
        })
        try:
            resp = await self.llm.generate(
                messages=ctx,
                model=config.EVOLUTION_CHARACTER_MODEL,
                temperature=config.EVOLUTION_CHARACTER_STANCE_TEMPERATURE,
                max_tokens=config.EVOLUTION_CHARACTER_MAX_TOKENS,
                reasoning_effort=config.EVOLUTION_CHARACTER_REASONING_EFFORT,
                caller="DirectorAgent-QueryParticipation",
            )
        except Exception as e:
            logger.warning("角色意愿询问失败 char=%s: %s", char_name, e)
            return {"stance": "不参与", "intervention_condition": None}
        return self._parse_stance(resp.content or "")

    @staticmethod
    def _parse_stance(content: str) -> dict:
        parts = re.split(r'介入条件[：:]?', content, maxsplit=1)
        stance_part = parts[0].strip()
        condition = parts[1].strip() if len(parts) == 2 and parts[1].strip() else None
        stance_text = re.sub(r'^\s*参与意愿[：:]?\s*', '', stance_part).strip()
        if "不参与" in stance_text:
            stance = "不参与"
        elif "有条件" in stance_text:
            stance = "有条件"
        elif "参与" in stance_text:
            stance = "参与"
        else:
            stance = "不参与"
        return {"stance": stance, "intervention_condition": condition}

    # ── notify_actor ──

    async def notify_actor(
        self, session: Session, character_id: str, perception: str
    ) -> dict | None:
        """通知指定角色在互动中行动。"""
        logger.info("📢 通知角色行动 char=%s session=%s", character_id, session.id)
        result = await self._retry_with_fallback(
            lambda: self._call_character(session, character_id, perception, "互动行动")
        )
        logger.debug("📢 角色行动完成 char=%s has_result=%s", character_id, result is not None)
        return result

    # ── write_timeline_event ──

    async def write_timeline_event(
        self, session: Session, event_type: str, event_content: str,
        character: str | None = None, source: str | None = None,
        motive: str | None = None, inner_thoughts: str | None = None,
        round_number: int | None = None,
    ) -> dict:
        """实时写入时间线事件到 SQLite 并通过 SSE 推送。"""
        event_dict: dict = {
            "type": event_type,
            "round": round_number if round_number is not None else session.current_round,
            "content": event_content,
        }
        if character is not None:
            event_dict["character"] = character
            char_config = session.world_config.get_character(character)
            if char_config and char_config.accent_color:
                event_dict["character_color"] = char_config.accent_color
        if source is not None:
            event_dict["source"] = source
        if motive is not None:
            event_dict["motive"] = motive
        if inner_thoughts is not None:
            event_dict["inner_thoughts"] = inner_thoughts

        try:
            await self.sessions.append_timeline_event(session.id, event_dict)
            await self.sse.broadcast(self._channel(session.id), {
                "type": "timeline_event",
                "data": {"event": event_dict},
            })
            logger.debug("📌 时间线写入 session=%s round=%d type=%s char=%s",
                        session.id, event_dict["round"], event_type, character or "-")
            return {"status": "success"}
        except Exception as e:
            logger.error("时间线写入失败 session=%s: %s", session.id, e)
            raise

    # ── write_round_summary ──

    async def write_round_summary(self, session: Session, summary: str) -> dict:
        """写入本轮叙事摘要。"""
        logger.info("📋 轮次摘要 session=%s round=%d", session.id, session.current_round)
        return await self.write_timeline_event(session, "round_summary", summary)

    # ── push_branches ──

    async def push_branches(self, session: Session, branches: list[dict]) -> dict:
        """推送 6 条剧情分支到前端。"""
        from server.ai.evolution_agent.agent import _session_branches, _pending_branches
        indexed = [{"index": i, **b} for i, b in enumerate(branches)]
        _session_branches[session.id] = indexed
        _pending_branches[session.id] = indexed
        logger.info("🌿 分支推送 session=%s count=%d", session.id, len(branches))

        await self.write_timeline_event(
            session, "branch_options",
            json.dumps(indexed, ensure_ascii=False))
        await self.sse.broadcast(self._channel(session.id), {
            "type": "branches",
            "data": {"branches": indexed},
        })
        return {"status": "success"}

    # ── push_validation_result ──

    async def push_validation_result(
        self, session: Session, validation: dict, message: str
    ) -> dict:
        """推送用户自定义事件校验结果。"""
        await self.sse.broadcast(self._channel(session.id), {
            "type": "validation_result",
            "data": {"valid": validation.get("valid", True),
                     "issues": validation.get("issues", []),
                     "message": message},
        })
        logger.info("🔧 校验结果推送 session=%s valid=%s message=%s",
                    session.id, validation.get("valid"), message)
        return {"status": "success"}

    # ── update_relationships ──

    async def update_relationships(
        self, session: Session, from_char: str, to_char: str, relationship: str
    ) -> dict:
        """更新角色关系连线并广播关系图谱。"""
        previous = session.relationships.get(from_char, {}).get(to_char)
        if from_char not in session.relationships:
            session.relationships[from_char] = {}
        session.relationships[from_char][to_char] = relationship
        logger.info("💞 关系更新 session=%s %s→%s: %s (was %s)",
                    session.id, from_char, to_char, relationship, previous)

        edge = {"from": from_char, "to": to_char, "relationship": relationship,
                "previous": previous}
        await self.write_timeline_event(
            session, "relationship",
            json.dumps({"edges": [edge]}, ensure_ascii=False))

        edges = [{"from": f, "to": t, "relationship": r}
                 for f, targets in session.relationships.items()
                 for t, r in targets.items()]
        await self.sse.broadcast(self._channel(session.id), {
            "type": "relationships",
            "data": {"edges": edges},
        })
        return {"status": "success"}


# ── 导演工具 JSON Schema ──

DIRECTOR_TOOL_SCHEMAS: dict[str, dict] = {
    "distribute_perceptions": {
        "type": "function",
        "function": {
            "name": "distribute_perceptions",
            "description": (
                "将增量感知视图并行发送给全部角色，角色产出行动。"
                "入参示例：{\"perceptions\": {\"角色A\": \"专属感知视图\", \"角色B\": \"专属感知视图\"}}；"
                "出参示例：{\"status\": \"success\"}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "perceptions": {"type": "object", "description": "角色名 → 增量感知视图"},
                },
                "required": ["perceptions"],
            },
        },
    },
    "query_interaction_stance": {
        "type": "function",
        "function": {
            "name": "query_interaction_stance",
            "description": (
                "询问所有角色参与互动的意愿和介入条件。回应仅记录在导演上下文。"
                "入参示例：{\"perceptions\": {\"角色A\": \"互动感知视图\", \"角色B\": \"互动感知视图\"}}；"
                "出参示例：{\"status\": \"success\"}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "perceptions": {"type": "object", "description": "角色名 → 互动感知视图"},
                },
                "required": ["perceptions"],
            },
        },
    },
    "notify_actor": {
        "type": "function",
        "function": {
            "name": "notify_actor",
            "description": (
                "通知指定角色在互动中行动。"
                "入参示例：{\"character_id\": \"林清雪\", \"perception\": \"墨渊向你走来…\"}；"
                "出参示例：{\"status\": \"success\"}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "character_id": {"type": "string", "description": "角色名"},
                    "perception": {"type": "string", "description": "该角色的增量感知视图"},
                },
                "required": ["character_id", "perception"],
            },
        },
    },
    "write_timeline_event": {
        "type": "function",
        "function": {
            "name": "write_timeline_event",
            "description": (
                "实时写入时间线事件并通过 SSE 推送。"
                "角色行动事件须填写 character 字段。"
                "角色如有动机须填写 motive 字段，不可省略。"
                "角色如有内心活动须填写 inner_thoughts 字段——从角色返回的「内心活动」中提炼，"
                "以第三人称上帝视角总结内心挣扎、情感转变与隐秘想法。"
                "入参示例：{\"event_type\": \"action\", \"event_content\": \"林清雪拔剑\", "
                "\"character\": \"林清雪\", \"motive\": \"保护弟子\", \"inner_thoughts\": \"不能让他再进一步\"}；"
                "出参示例：{\"status\": \"success\"}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type": {
                        "type": "string",
                        "enum": ["action", "conflict", "director_path", "scene_setting", "user_decision"],
                    },
                    "event_content": {"type": "string"},
                    "character": {"type": "string"},
                    "motive": {"type": "string"},
                    "inner_thoughts": {"type": "string"},
                },
                "required": ["event_type", "event_content"],
            },
        },
    },
    "write_round_summary": {
        "type": "function",
        "function": {
            "name": "write_round_summary",
            "description": (
                "写入本轮叙事线索型摘要。"
                "入参示例：{\"summary\": \"**叙事脉络**\\n场景名…\\n**角色弧线**\\n…\"}；"
                "出参示例：{\"status\": \"success\"}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "自然语言叙事文本"},
                },
                "required": ["summary"],
            },
        },
    },
    "push_branches": {
        "type": "function",
        "function": {
            "name": "push_branches",
            "description": (
                "推送 6 条剧情分支到前端。"
                "入参示例：{\"branches\": [{\"title\": \"分支标题\", \"description\": \"描述\", \"reason\": \"推荐理由\"}]}；"
                "出参示例：{\"status\": \"success\"}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "branches": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "reason": {"type": "string"},
                            },
                            "required": ["title", "description", "reason"],
                        },
                    },
                },
                "required": ["branches"],
            },
        },
    },
    "push_validation_result": {
        "type": "function",
        "function": {
            "name": "push_validation_result",
            "description": (
                "推送用户自定义事件校验结果。"
                "入参示例：{\"validation\": {}, \"message\": \"校验通过\"}；"
                "出参示例：{\"status\": \"success\"}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "validation": {"type": "object", "description": "校验结果对象"},
                    "message": {"type": "string", "description": "提示信息"},
                },
                "required": ["validation", "message"],
            },
        },
    },
    "update_relationships": {
        "type": "function",
        "function": {
            "name": "update_relationships",
            "description": (
                "更新角色关系连线。"
                "入参示例：{\"from_char\": \"墨渊\", \"to_char\": \"林清雪\", \"relationship\": \"亦师亦友\"}；"
                "出参示例：{\"status\": \"success\"}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "from_char": {"type": "string"},
                    "to_char": {"type": "string"},
                    "relationship": {"type": "string"},
                },
                "required": ["from_char", "to_char", "relationship"],
            },
        },
    },
}
