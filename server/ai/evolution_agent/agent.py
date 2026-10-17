# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""演化管线编排器。

流程：冲突潜质扫描 → 场景设定 → 感知派发与收集行动 → 路径判断 → 轮次收束 → 持久化。
"""

import asyncio
import json
import logging
import re

from server.config import config
from server.services.session_manager import (
    Session, SessionStatus, SessionManager,
)
from server.sse.sse_manager import SSEManager
from server.ai.common.llm_client import LLMClient
from server.ai.evolution_agent.director_tools import DirectorTools, DIRECTOR_TOOL_SCHEMAS

logger = logging.getLogger(__name__)


def compute_max_notifies(char_count: int) -> int:
    """互动环节单轮 notify_actor 上限：min(角色数 × 3, 15)。"""
    return min(char_count * 3, 15)

# ── 共享状态：orchestrator ↔ REST router ──

_session_events: dict[str, asyncio.Event] = {}
_session_decisions: dict[str, dict] = {}
_session_branches: dict[str, list[dict]] = {}
_pending_branches: dict[str, list[dict]] = {}
DIRECTOR_ALL_TOOLS: list[dict] = []
ALL_TOOL_NAMES: set[str] = set()


def get_session_branches(session_id: str) -> list[dict] | None:
    """REST router 调用：获取会话待选分支。"""
    return _session_branches.get(session_id)


def resolve_session_event(session_id: str, decision_type: str, decision_data: dict) -> bool:
    """REST router 调用：唤醒 orchestrator 中等待的 asyncio.Event。"""
    event = _session_events.get(session_id)
    if event is None:
        return False
    _session_decisions[session_id] = {"type": decision_type, "data": decision_data}
    event.set()
    return True


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


class PipelineOrchestrator:
    """核心编排器——串联完整的单轮演化生命周期。"""

    def __init__(self, llm_client: LLMClient, session_manager: SessionManager,
                 sse_manager: SSEManager):
        self.llm = llm_client
        self.sessions = session_manager
        self.sse = sse_manager
        self.tools = DirectorTools(llm_client, session_manager, sse_manager)

        global DIRECTOR_ALL_TOOLS
        DIRECTOR_ALL_TOOLS = [
            {"type": "function", "function": v["function"]}
            for v in DIRECTOR_TOOL_SCHEMAS.values()
        ]
        global ALL_TOOL_NAMES
        ALL_TOOL_NAMES = {t["function"]["name"] for t in DIRECTOR_ALL_TOOLS}

    def _channel(self, session_id: str) -> str:
        return f"evolution:{session_id}"

    async def _maybe_compact_director_context(self, session: Session):
        """导演上下文超阈值时用时间线 round_summary 重建（决策 D6）。

        保留 system 消息与最近两轮完整原文，中段替换为 [历史压缩] user 消息
        （全部轮次摘要 + 路径判定一行式）。切分点位于某条 `[第 N 轮]` user
        消息开头，不产生半轮截断。压缩只改内存，轮末随 _persist_contexts 落盘。
        """
        def _ctx_size(msgs: list[dict]) -> int:
            total = 0
            for m in msgs:
                total += len(str(m.get("content") or ""))
                total += len(json.dumps(m.get("tool_calls") or [], ensure_ascii=False))
            return total

        if _ctx_size(session.director_context) < config.EVOLUTION_COMPACT_THRESHOLD_CHARS:
            return

        round_num = session.current_round            # run_round 开头已自增
        keep_from_round = max(1, round_num - 2)      # 保留 keep_from_round..round_num-1 两轮

        timeline = await self.sessions.get_timeline(session.id)
        digest_parts: list[str] = []
        for e in timeline:
            if e.get("type") == "round_summary":
                digest_parts.append(f"### 第 {e.get('round')} 轮摘要\n{e.get('content', '')}")
            elif e.get("type") == "director_path":
                content = str(e.get("content", "")).replace("\n", " ")
                digest_parts.append(f"- 第 {e.get('round')} 轮路径判定：{content[:120]}")
        digest = "\n\n".join(digest_parts) or "（无轮次摘要）"

        cut = len(session.director_context)
        for i, m in enumerate(session.director_context):
            content = str(m.get("content") or "")
            if m.get("role") == "user" and content.startswith("[第"):
                match = re.match(r"\[第 (\d+) 轮\]", content)
                if match and int(match.group(1)) >= keep_from_round:
                    cut = i
                    break

        session.director_context = (
            [session.director_context[0]]
            + [{"role": "user",
                "content": (f"[历史压缩] 第 1..{keep_from_round - 1} 轮官方轮次摘要如下：\n\n"
                            f"{digest}")}]
            + session.director_context[cut:]
        )
        logger.info("🗜️ 导演上下文已压缩 session=%s 保留轮次>=%d 消息数=%d",
                    session.id, keep_from_round, len(session.director_context))

    # ── 主入口 ──

    async def run_round(self, session_id: str):
        """执行完整的单轮生命周期。"""
        session = await self.sessions.get(session_id)
        session.status = SessionStatus.RUNNING
        session.current_round += 1
        round_num = session.current_round

        logger.info("🔄 轮次开始 session=%s round=%d/%d",
                    session_id, round_num, session.max_rounds)

        await self.sse.broadcast(self._channel(session_id), {
            "type": "round_start",
            "data": {"round": round_num, "max_rounds": session.max_rounds},
        })

        await self._maybe_compact_director_context(session)

        try:
            if round_num == 1:
                ie = session.world_config.initial_event
                initial_text = f"{ie.content}（{ie.time}）"
                await self.tools.write_timeline_event(session, "scene_setting", initial_text, round_number=0)
                for char in session.world_config.characters:
                    for target, attitude in char.attitudes.items():
                        session.relationships.setdefault(char.name, {})[target] = attitude
                edges = [
                    {"from": char.name, "to": target, "relationship": attitude,
                     "previous": None}
                    for char in session.world_config.characters
                    for target, attitude in char.attitudes.items()
                ]
                if edges:
                    await self.tools.write_timeline_event(
                        session, "relationship",
                        json.dumps({"edges": edges}, ensure_ascii=False))
                    await self.sse.broadcast(self._channel(session_id), {
                        "type": "relationships",
                        "data": {"edges": edges},
                    })

            # 步骤 0：冲突潜质扫描
            logger.info("📋 [步骤0] 冲突潜质扫描 session=%s", session_id)
            await self._execute_director_step(
                session,
                "步骤0：冲突潜质扫描。\n"
                "扫描目标冲突、背景钩子、规则张力、关系裂缝，\n"
                "选择叙事上最成熟的 1-2 个点，明确写出你的分析结论，为后续步骤提供线索方向。\n"
                "本步骤不调用任何工具，请将分析结果直接输出在回复中。",
                only_tools=set(),
            )

            # 步骤 1：场景设定
            logger.info("📋 [步骤1] 场景设定 session=%s", session_id)
            await self._execute_director_step(
                session,
                "步骤1：场景设定。\n"
                "使用 write_timeline_event（event_type=scene_setting，不填 character），\n"
                "以第三人称上帝视角描述本轮开场时各角色的位置、状态和当前场景。\n"
                "基于上一轮的轮次摘要和最新事件（首轮则基于初始事件），锁定本轮叙事的起点。\n"
                "在场景描述中铺设步骤 0 扫描识别的环境线索。2-3 句足矣。\n"
                "直接调用工具，不要输出分析文字。写入一个事件后立即停止，不要做步骤 2/3/4 的事。",
                only_tools={"write_timeline_event"},
            )

            # 步骤 2：感知派发与收集行动
            logger.info("📋 [步骤2] 感知派发与收集行动 session=%s", session_id)
            step_2_prompt = (
                "步骤2：感知派发与收集行动。\n"
                "1）基于步骤 0 的扫描结果，在不违反信息不对称的前提下，\n"
                "在角色的感知视图中植入可触发过往经历的环境线索。\n"
                "2）按出场聚焦规则确定本轮聚焦名单（≤5 人世界即全部角色；>5 人世界为 3-5 名），\n"
                "使用 distribute_perceptions 一次性派发感知：聚焦角色获完整感知，名单外角色获简短感知。\n"
                "3）使用 write_timeline_event 写入角色行动（event_type=action，须填 character）：\n"
                "聚焦角色写深度行动（须含 motive，如有内心活动填 inner_thoughts）；\n"
                "名单外角色仅在有值得记录的低介入度反应时写入简短行动，无则静默。\n"
                "event_content 为角色行动（第三人称），\n"
                "角色如有动机须填 motive 字段（不可省略），\n"
                "角色如有内心活动须填 inner_thoughts 字段——从角色返回的「内心活动」中提炼，\n"
                "以第三人称上帝视角总结。\n"
                "每个角色只派发一次感知、收集一次行动。\n"
                "直接调用工具，不要输出分析文字。完成后立即停止，不要做步骤 3/4 的事。"
            )
            await self._execute_director_step(
                session,
                step_2_prompt,
                only_tools={"distribute_perceptions", "write_timeline_event"},
            )

            # 步骤 3：路径判断
            logger.info("📋 [步骤3] 路径判断 session=%s", session_id)
            path = await self._judge_path(session)
            logger.info("🔀 路径判定 session=%s path=%s", session_id, path)

            if path == "conflict":
                await self._handle_conflict(session)
            elif path == "interaction":
                await self._handle_interaction(session)

            # 步骤 4：轮次收束
            logger.info("📋 [步骤4] 轮次收束 session=%s", session_id)
            await self._execute_director_step(
                session,
                "步骤4：轮次收束。仅做两件事。\n"
                "1）使用 update_relationships 更新角色关系变化。\n"
                "2）使用 write_round_summary 写入本轮叙事摘要。\n"
                "冲突标记和用户决策已由系统自动写入，round_summary 中自然融入即可。\n"
                "直接调用工具，不要输出分析文字。更新关系和摘要后立即停止。",
                only_tools={"update_relationships", "write_round_summary"},
            )

        except Exception as e:
            logger.exception("轮次执行异常 session=%s: %s", session_id, e)
            await self.sse.broadcast(self._channel(session_id), {
                "type": "error",
                "data": {"code": "ROUND_ERROR", "message": f"轮次执行异常: {e}"},
            })

        await self._finalize_round(session)
        await self._persist_contexts(session)
        await self.sessions.update_meta(session_id,
                                        status=session.status.value,
                                        current_round=session.current_round)

    # ── 上下文持久化 ──

    async def _persist_contexts(self, session: Session):
        try:
            dir_msgs = len(session.director_context)
            char_sizes = {n: len(c) for n, c in session.character_contexts.items()}
            logger.info("💾 持久化上下文 session=%s director_msgs=%d char_sizes=%s",
                       session.id, dir_msgs, char_sizes)
            if session.relationships:
                await asyncio.gather(
                    self.sessions.set_context(session.id, "director", session.director_context),
                    self.sessions.set_relationships(session.id, session.relationships),
                )
            else:
                await self.sessions.set_context(session.id, "director", session.director_context)
            for char_name, ctx in session.character_contexts.items():
                await self.sessions.set_context(session.id, char_name, ctx)
        except Exception as e:
            logger.error("上下文持久化失败 session=%s: %s", session.id, e)

    # ── 轮次收束 ──

    async def _finalize_round(self, session: Session):
        if session.current_round >= session.max_rounds:
            session.status = SessionStatus.ENDED
            logger.info("🏁 演化额度用完 session=%s round=%d", session.id, session.current_round)
            await self.sse.broadcast(self._channel(session.id), {
                "type": "session_ended",
                "data": {"reason": "rounds_exhausted",
                         "message": f"演化额度已用完（{session.current_round}/{session.max_rounds}）"},
            })
        else:
            session.status = SessionStatus.WAITING_NEXT_ROUND
            remaining = session.max_rounds - session.current_round
            logger.info("✅ 轮次完成 session=%s round=%d remaining=%d",
                        session.id, session.current_round, remaining)
            await self.sse.broadcast(self._channel(session.id), {
                "type": "round_end",
                "data": {"round": session.current_round, "remaining_rounds": remaining},
            })

    # ── 导演步骤执行 ──

    async def _execute_director_step(
        self, session: Session, instruction: str,
        only_tools: set[str] | None = None,
        action_source: str | None = None,
    ):
        session.director_context.append({
            "role": "user",
            "content": f"[第 {session.current_round} 轮] {instruction}",
        })

        exclude_tools = ALL_TOOL_NAMES - only_tools if only_tools is not None else None
        tools = DIRECTOR_ALL_TOOLS
        if exclude_tools:
            tools = [t for t in DIRECTOR_ALL_TOOLS
                     if t["function"]["name"] not in exclude_tools]

        max_loops = 20
        empty_retried = False
        tools_available = [t["function"]["name"] for t in tools]
        logger.info("  🎬 导演步骤开始 session=%s round=%d tools=%s",
                    session.id, session.current_round, tools_available)
        for loop_idx in range(max_loops):
            try:
                resp = await self.llm.generate(
                    messages=session.director_context,
                    model=config.EVOLUTION_DIRECTOR_MODEL,
                    caller="DirectorAgent",
                    tools=tools,
                    max_tokens=config.EVOLUTION_DIRECTOR_MAX_TOKENS,
                    temperature=config.EVOLUTION_DIRECTOR_TEMPERATURE,
                    reasoning_effort=config.EVOLUTION_DIRECTOR_REASONING_EFFORT,
                )
            except Exception as e:
                logger.warning("导演 LLM 调用失败 session=%s: %s", session.id, e)
                break

            # 空响应重试：模型偶发返回空内容且无工具调用，重试一次
            if not resp.tool_calls and not (resp.content or "").strip() and not empty_retried:
                reasoning = resp.reasoning_content or ""
                logger.warning(
                    "导演空响应 session=%s 将重试 reasoning=%s",
                    session.id, reasoning[-500:] if reasoning else "(无思考内容)",
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
            # elif "content" not in assistant_msg and resp.reasoning_content:
            #     # 思考模式下模型可能只输出 reasoning 而无 content
            #     assistant_msg["content"] = resp.reasoning_content
            elif "content" not in assistant_msg:
                assistant_msg["content"] = ""

            # 导演 LLM 响应日志
            content = resp.content or ""
            content_len = len(content)
            tc_names = [tc["function"]["name"] for tc in (resp.tool_calls or [])]
            tokens = resp.usage.total_tokens if resp.usage else 0
            logger.info(
                "  🤖 导演响应 session=%s loop=%d tokens=%d content_len=%d tool_calls=%s",
                session.id, loop_idx, tokens, content_len, tc_names,
            )
            if content:
                preview = content[:300].replace('\n', '\\n')
                logger.info("  💬 导演输出内容 session=%s: %s%s",
                           session.id, preview, "…" if content_len > 300 else "")

            session.director_context.append(assistant_msg)

            if not resp.tool_calls:
                logger.info("  ✅ 导演步骤完成（无工具调用） session=%s loop=%d",
                           session.id, loop_idx)
                break

            for tc in resp.tool_calls:
                tool_name = tc["function"]["name"]
                if exclude_tools and tool_name in exclude_tools:
                    tool_result = {
                        "status": "error",
                        "message": (
                            f"工具 {tool_name} 在当前步骤不可用。"
                            f"请仅使用当前步骤允许的工具，完成后停止，不要尝试替代方案。"
                        ),
                    }
                else:
                    tool_result = await self._execute_director_tool(session, tc, action_source)
                session.director_context.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(tool_result, ensure_ascii=False),
                })
        else:
            logger.warning("导演循环耗尽 session=%s", session.id)

    async def _execute_director_tool(self, session: Session, tool_call: dict,
                                    action_source: str | None = None) -> dict:
        name = tool_call["function"]["name"]
        raw_args = tool_call["function"]["arguments"]
        args = _safe_parse_json(raw_args, name)

        logger.debug("🔧 导演工具 session=%s round=%d tool=%s",
                     session.id, session.current_round, name)

        if name == "distribute_perceptions":
            perceptions = args.get("perceptions", {})
            result = await self.tools.distribute_perceptions(session, perceptions)
            logger.info("  📡 感知派发完成 session=%s chars=%d results=%d",
                       session.id, len(perceptions), len(result))
            return result
        elif name == "query_interaction_stance":
            perceptions = args.get("perceptions", {})
            result = await self.tools.query_interaction_stance(session, perceptions)
            stances = {n: r.get("stance", "?") for n, r in result.items()}
            logger.info("  ❓ 互动意愿收集完成 session=%s stances=%s",
                       session.id, stances)
            return result
        elif name == "notify_actor":
            char_id = args.get("character_id", "")
            result = await self.tools.notify_actor(session, char_id, args.get("perception", ""))
            has_action = bool(result and result.get("action"))
            logger.info("  📢 角色行动通知完成 char=%s has_action=%s", char_id, has_action)
            return result
        elif name == "write_timeline_event":
            if not args:
                logger.warning(
                    "write_timeline_event 参数解析失败 session=%s raw=%.200s...",
                    session.id, raw_args)
                return {"status": "error", "message": "参数解析失败，无法写入时间线事件"}
            result = await self.tools.write_timeline_event(
                session, args.get("event_type", "action"), args.get("event_content", ""),
                args.get("character"), action_source,
                args.get("motive"), args.get("inner_thoughts"))
            logger.info("  📝 时间线写入 session=%s type=%s char=%s round=%d",
                       session.id, args.get("event_type"),
                       args.get("character") or "-", session.current_round)
            return result
        elif name == "write_round_summary":
            result = await self.tools.write_round_summary(
                session, args.get("summary", ""))
            logger.info("  📋 轮次摘要写入 session=%s len=%d",
                       session.id, len(args.get("summary", "")))
            return result
        elif name == "push_branches":
            branches = args.get("branches", [])
            result = await self.tools.push_branches(session, branches)
            logger.info("  🌿 分支推送 session=%s count=%d", session.id, len(branches))
            return result
        elif name == "push_validation_result":
            result = await self.tools.push_validation_result(
                session, args.get("validation", {}), args.get("message", ""))
            logger.info("  ✅ 校验结果推送 session=%s valid=%s",
                       session.id, args.get("validation", {}).get("valid"))
            return result
        elif name == "update_relationships":
            result = await self.tools.update_relationships(
                session, args.get("from_char", ""), args.get("to_char", ""),
                args.get("relationship", ""))
            logger.info("  💞 关系更新 session=%s %s→%s: %s",
                       session.id, args.get("from_char"),
                       args.get("to_char"), args.get("relationship", ""))
            return result
        else:
            logger.warning("未知导演工具: %s", name)
            return {"status": "error", "message": f"未知工具: {name}"}

    # ── 路径判断 ──

    async def _judge_path(self, session: Session) -> str:
        instruction = (
            "步骤3：基于本轮角色行动判断路径。\n"
            "按以下四维度逐项检查：\n"
            "1. 目标冲突——角色本轮行动是否与他人的核心目标产生碰撞？\n"
            "2. 规则违反——是否有角色行动触碰世界规则的边界？\n"
            "3. 关系触发——角色行动是否触及他人过往经历中的敏感点？\n"
            "4. 空间交集——是否有两个及以上角色的行动在空间上产生交集？\n"
            "调用 write_timeline_event（event_type=director_path，不填 character），\n"
            "event_content 中逐项写出四维度检查结果和最终判定路径\n"
            "（英文关键词：conflict / interaction / none）。"
        )
        session.director_context.append({
            "role": "user",
            "content": f"[第 {session.current_round} 轮] {instruction}",
        })

        tools = [t for t in DIRECTOR_ALL_TOOLS
                 if t["function"]["name"] == "write_timeline_event"]

        try:
            resp = await self.llm.generate(
                messages=session.director_context,
                model=config.EVOLUTION_DIRECTOR_MODEL,
                temperature=0.3,
                max_tokens=config.EVOLUTION_DIRECTOR_MAX_TOKENS,
                caller="DirectorAgent",
                reasoning_effort=config.EVOLUTION_DIRECTOR_REASONING_EFFORT,
                tools=tools,
            )
        except Exception as e:
            logger.error("路径判断 LLM 失败 session=%s: %s", session.id, e)
            return "none"

        # 构建 assistant 消息
        assistant_msg: dict = {"role": "assistant"}
        if resp.content is not None:
            assistant_msg["content"] = resp.content
        tc_list = resp.tool_calls or []
        if tc_list:
            assistant_msg["tool_calls"] = tc_list
            if resp.reasoning_content:
                assistant_msg["reasoning_content"] = resp.reasoning_content
        elif "content" not in assistant_msg:
            assistant_msg["content"] = ""

        session.director_context.append(assistant_msg)

        # 提取路径判定
        path = "none"
        raw_args = ""
        if tc_list:
            tc = tc_list[0]
            raw_args = tc["function"]["arguments"]
            args = _safe_parse_json(raw_args, "write_timeline_event")
            event_type = args.get("event_type", "") if args else ""
            event_content = args.get("event_content", "") if args else ""

            if event_type:
                # 执行工具调用，写入 timeline
                result = await self.tools.write_timeline_event(
                    session, event_type, event_content,
                    args.get("character"), None,
                    args.get("motive"), args.get("inner_thoughts"),
                )
                session.director_context.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })
                logger.info("  📝 路径判断写入 timeline session=%s type=%s",
                           session.id, event_type)

            # 从 event_content 中解析路径
            content_lower = event_content.lower()
            if "conflict" in content_lower:
                path = "conflict"
            elif "interaction" in content_lower:
                path = "interaction"
            else:
                path = "none"
        else:
            # 降级：模型未调用工具，从文本内容解析
            content = resp.content or ""
            content_lower = content.lower()
            if "conflict" in content_lower:
                path = "conflict"
            elif "interaction" in content_lower:
                path = "interaction"

        content_preview = (resp.content or "")[:300].replace('\n', '\\n')
        tokens = resp.usage.total_tokens if resp.usage else 0
        logger.info("  🔀 路径判断 session=%s path=%s tokens=%d raw_args=%.200s content=%s%s",
                   session.id, path, tokens, raw_args,
                   content_preview, "…" if len(resp.content or "") > 300 else "")
        return path

    # ── 冲突处理 ──

    async def _handle_conflict(self, session: Session):
        logger.info("⚡ 冲突处理 session=%s round=%d", session.id, session.current_round)
        await self._execute_director_step(
            session,
            "步骤3.1：冲突处理。仅做三件事。\n"
            "1）使用 write_timeline_event 写入冲突标记（event_type=conflict）。\n"
            "2）使用 push_branches 生成 6 条分支并推送到前端。\n"
            "3）完成后停止，等待用户选择。\n"
            "直接调用工具，不要输出分析文字。不要自行推进剧情、不要写摘要。",
            only_tools={"write_timeline_event", "push_branches"},
        )

        event = asyncio.Event()
        _session_events[session.id] = event
        session.status = SessionStatus.PAUSED
        await self._persist_contexts(session)
        await self.sessions.update_meta(session.id, status=session.status.value)

        logger.info("⏸️ 会话挂起 session=%s reason=conflict", session.id)
        await self.sse.broadcast(self._channel(session.id), {
            "type": "session_paused",
            "data": {"reason": "conflict", "message": "检测到冲突，请选择剧情分支或输入自定义事件"},
        })

        await event.wait()

        decision = _session_decisions.pop(session.id, {})
        user_decision_type = decision.get("type")
        user_decision_data = decision.get("data")

        pending_branches = _session_branches.pop(session.id, None)
        _pending_branches.pop(session.id, None)
        _session_events.pop(session.id, None)

        session.status = SessionStatus.RUNNING
        branch_info = ""
        if user_decision_type == "branch":
            branch_index = user_decision_data["branch_index"]
            if pending_branches and branch_index < len(pending_branches):
                b = pending_branches[branch_index]
                branch_info = f"「{b.get('title', '')}」——{b.get('description', '')}"
            summary = f"选择分支：{branch_info}" if branch_info else f"选择分支：{branch_index}"
            logger.info("▶️ 冲突恢复 session=%s decision=branch", session.id)
        else:
            event_text = user_decision_data["event_text"]
            validation = await self._validate_custom_event(session, event_text)
            await self.sse.broadcast(self._channel(session.id), {
                "type": "validation_result", "data": validation,
            })
            summary = f"自定义事件：{event_text}"
            logger.info("▶️ 冲突恢复 session=%s decision=custom_event", session.id)

        notification = f"已做出选择：{summary}。"
        if branch_info:
            notification += f"\n分支内容：{branch_info}"
        notification += (
            "\n请继续推进剧情。注意：用户决策已作为独立时间线事件写入，"
            "你在 round_summary 中自然融入即可。"
        )
        session.director_context.append({
            "role": "user",
            "content": f"[系统通知] {notification}",
        })

        await self.tools.write_timeline_event(session, "user_decision", summary)

    # ── 互动处理 ──

    async def _handle_interaction(self, session: Session):
        char_count = len(session.character_contexts)
        max_notifies = compute_max_notifies(char_count)
        logger.info("💬 [步骤3.2] 互动处理 session=%s round=%d chars=%d max_notifies=%d",
                   session.id, session.current_round, char_count, max_notifies)
        await self._execute_director_step(
            session,
            "步骤3.2：互动处理。\n"
            "1）使用 query_interaction_stance 询问所有角色互动意愿。\n"
            "2）使用 notify_actor 串行推动角色间多轮回合对话，\n"
            f"最多 {max_notifies} 次 notify_actor，达到后必须自然收束。\n"
            "3）每次角色行动后立即用 write_timeline_event 写入时间线（event_type=action，须填 character）。\n"
            "event_content 为角色行动（第三人称），\n"
            "角色如有动机须填 motive 字段（不可省略），\n"
            "角色如有内心活动须填 inner_thoughts 字段——从角色返回的「内心活动」中提炼。\n"
            "不要写分析/标签/调度记录/冲突自评。\n"
            "直接调用工具，不要输出分析文字。互动收束后立即停止，不要写摘要、不要推分支。",
            only_tools={"query_interaction_stance", "notify_actor", "write_timeline_event"},
            action_source="interaction",
        )

    async def _validate_custom_event(self, session: Session, event_text: str) -> dict:
        session.director_context.append({
            "role": "user",
            "content": (
                f"用户提交了自定义事件：'{event_text}'。"
                f"请校验该事件是否与当前世界观一致。"
                f"返回 JSON：{{\"valid\": true/false, \"issues\": [\"问题描述\"]}}。"
            ),
        })
        try:
            resp = await self.llm.generate(
                messages=session.director_context,
                model=config.EVOLUTION_DIRECTOR_MODEL,
                temperature=config.EVOLUTION_DIRECTOR_TEMPERATURE,
                max_tokens=config.EVOLUTION_DIRECTOR_MAX_TOKENS,
                caller="DirectorAgent",
                reasoning_effort=config.EVOLUTION_DIRECTOR_REASONING_EFFORT,
            )
        except Exception as e:
            logger.error("自定义事件校验失败 session=%s: %s", session.id, e)
            return {"valid": False, "issues": ["校验失败：LLM 无响应"]}

        assistant_msg: dict = {"role": "assistant", "content": resp.content or ""}
        # DeepSeek 思考模式：_validate_custom_event 无工具调用，reasoning_content 无需回传
        session.director_context.append(assistant_msg)

        try:
            return json.loads(resp.content or "{}")
        except json.JSONDecodeError:
            return {"valid": True, "issues": []}
