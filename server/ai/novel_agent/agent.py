# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""小说生成 Agent——多轮 Agent-Reviewer 循环，单一自治 Agent 通过工具调用完成全书创作。"""

import json
import logging
import re
import uuid
from pathlib import Path

from server.config import config
from server.storage.sqlite_client import now_ms
from server.prompt_loader import get_prompt
from server.ai.common.llm_client import LLMClient
from .tools import (
    write_file, read_file, review_chapter, assemble,
    _count_chinese_chars, _make_chars_verdict, _resolve_path,
)

logger = logging.getLogger(__name__)


class NovelAgent:
    """单一自治 Agent，通过工具调用完成小说创作全流程。"""

    def __init__(self):
        self._llm = LLMClient(config)

    def _build_system_prompt(self) -> str:
        text = get_prompt("novel_agent/agent_system")
        return text.replace(
            "{chapter_min_chars}", str(config.NOVEL_CHAPTER_MIN_CHARS)
        ).replace(
            "{chapter_max_chars}", str(config.NOVEL_CHAPTER_MAX_CHARS)
        )

    def _build_first_user_message(
        self,
        world_config: dict,
        characters: list[dict],
        initial_event: dict,
        timeline_events: list[dict],
    ) -> str:
        template = get_prompt("novel_agent/first_user_message")
        text = template.replace("{world.name}", world_config.get("name", ""))
        text = text.replace("{world.description}", world_config.get("description", ""))
        text = text.replace("{world.world_history}", world_config.get("world_history", ""))
        text = text.replace("{world.rules}", world_config.get("rules", ""))

        char_parts = []
        for c in characters:
            name = c.get("name", "未知角色")
            parts = [
                f"#### {name}",
                f"- **身份**：{c.get('identity', '未知')}",
                f"- **性格**：{c.get('personality', '未知')}",
                f"- **语言风格**：{c.get('speech_style', '无')}",
                f"- **核心目标**：{c.get('goal', '未知')}",
            ]
            if c.get("backstory"):
                parts.append(f"- **背景故事**：{c['backstory']}")
            if c.get("initial_location"):
                parts.append(f"- **初始位置**：{c['initial_location']}")
            if c.get("initial_state"):
                parts.append(f"- **初始状态**：{c['initial_state']}")
            char_parts.append("\n".join(parts))
        text = text.replace("{characters}", "\n\n".join(char_parts))

        text = text.replace("{initial_event.content}", initial_event.get("content", ""))
        text = text.replace("{initial_event.time}", initial_event.get("time", ""))

        timeline_parts = []
        for e in timeline_events:
            etype = e.get("type", "")
            if etype in ("round_summary", "branch_options", "director_path"):
                continue
            content = e.get("content", "")
            if etype == "action":
                char = e.get("character", "?")
                motive = e.get("motive", "")
                inner = e.get("inner_thoughts", "")
                line = f"- [{etype}] **{char}** {content}"
                if motive:
                    line += f"\n  - 动机：{motive}"
                if inner:
                    line += f"\n  - 内心想法：{inner}"
            elif etype == "scene_setting":
                line = f"\n### 🌄 场景锚点（第{e.get('round', '?')}轮）\n\n{content}\n"
            else:
                line = f"- [{etype}] {content}"
            timeline_parts.append(line)
        text = text.replace("{timeline events}", "\n".join(timeline_parts))

        return text

    async def _execute_tool(
        self, tool_name: str, tool_args: dict, tool_call_id: str,
        work_dir: Path, *, reviewer_system_prompt: str,
    ) -> dict:
        if tool_name == "write_file":
            return write_file(work_dir, tool_args.get("path", ""),
                              tool_args.get("content", ""))
        elif tool_name == "read_file":
            return read_file(work_dir, tool_args.get("path", ""),
                             tool_args.get("search"))
        elif tool_name == "review_chapter":
            return await review_chapter(
                work_dir=work_dir,
                chapter_index=tool_args.get("chapter_index", 0),
                chapter_path=tool_args.get("chapter_path", ""),
                llm_client=self._llm,
                reviewer_system_prompt=reviewer_system_prompt,
                reviewer_model=config.NOVEL_REVIEWER_MODEL,
                reviewer_reasoning_effort=config.NOVEL_REVIEWER_REASONING_EFFORT,
                reviewer_max_tokens=config.NOVEL_REVIEWER_MAX_TOKENS,
                chapter_min_chars=config.NOVEL_CHAPTER_MIN_CHARS,
                chapter_max_chars=config.NOVEL_CHAPTER_MAX_CHARS,
            )
        elif tool_name == "assemble":
            return assemble(work_dir)
        else:
            return {"success": False, "error": f"未知工具: {tool_name}"}

    def _safe_parse_tool_args(self, tc: dict, turns: int) -> dict | None:
        try:
            return json.loads(tc["function"]["arguments"])
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("turn %d: 工具参数 JSON 解析失败: %s", turns, e)
            return None

    async def _broadcast_sse(self, sse_manager, task_id: str, event: dict):
        if sse_manager is None:
            return
        try:
            await sse_manager.broadcast(f"novel:{task_id}", event)
        except Exception as e:
            logger.warning("SSE 广播失败 channel=novel:%s: %s", task_id, e)

    async def generate(
        self,
        task_id: str,
        world_config: dict,
        characters: list[dict],
        initial_event: dict,
        timeline_events: list[dict],
        sse_manager=None,
    ) -> dict:
        """启动 Agent 循环，返回 NovelResult。"""
        logger.info("=" * 40)
        logger.info("NovelAgent 启动 task_id=%s world=%s",
                    task_id, world_config.get("name", "?"))
        logger.info("角色 %d 个 | 时间线事件 %d 条 | 字数 %d-%d",
                    len(characters), len(timeline_events),
                    config.NOVEL_CHAPTER_MIN_CHARS, config.NOVEL_CHAPTER_MAX_CHARS)

        await self._broadcast_sse(sse_manager, task_id, {
            "type": "started", "task_id": task_id,
            "world_name": world_config.get("name", ""),
            "character_count": len(characters),
        })

        # 1. 创建工作目录
        base = Path(config.NOVEL_WORK_DIR_BASE)
        if not base.is_absolute():
            _project_root = Path(__file__).resolve().parent.parent.parent.parent
            base = _project_root / config.NOVEL_WORK_DIR_BASE
        work_dir = base / task_id
        traces_dir = work_dir / "traces"
        traces_dir.mkdir(parents=True, exist_ok=True)
        logger.info("工作目录: %s", work_dir)

        # 2. 构建 prompts
        system_prompt = self._build_system_prompt()
        reviewer_system_prompt = get_prompt("novel_agent/reviewer_system")
        first_msg = self._build_first_user_message(
            world_config, characters, initial_event, timeline_events)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": first_msg},
        ]

        # 3. 工具 schema
        tools_schema = [
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "写入内容到文件。覆盖写入——同名文件再次调用即更新。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "相对路径，如 chapters/ch_1.md"},
                            "content": {"type": "string", "description": "要写入的完整文本"},
                        },
                        "required": ["path", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "读取文件内容。不传 search 返回全文；传 search 返回匹配摘录。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "search": {"type": "string", "description": "可选关键词（1-30 字符）"},
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "review_chapter",
                    "description": "将当前章提交独立审稿人审查。写完一章或修订后调用。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "chapter_index": {"type": "integer", "description": "章节序号，从 1 开始"},
                            "chapter_path": {"type": "string", "description": "如 chapters/ch_3.md"},
                        },
                        "required": ["chapter_index", "chapter_path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "assemble",
                    "description": "扫描 chapters/ 下所有 ch_N.md，拼合为全书。调用即宣告完成。",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

        # 4. 循环状态
        turns = 0
        _current_doc = None
        _doc_cycles = 0
        _doc_reviews = 0
        _rollback_count = 0
        _cumul_tokens = 0
        _chapter_progress = {}
        _temp_checkpoint = {"messages_len": len(messages), "doc_cycles": 0,
                            "doc_reviews": 0, "current_doc": None}
        _checkpoint = _temp_checkpoint.copy()

        _trace_fh = open(traces_dir / f"{task_id}.jsonl", "w", encoding="utf-8")

        def _write_trace(record: dict):
            record.setdefault("timestamp", now_ms())
            try:
                _trace_fh.write(json.dumps(record, ensure_ascii=False, default=repr) + "\n")
                _trace_fh.flush()
            except Exception:
                pass

        try:
            while turns < config.NOVEL_MAX_TURNS:
                logger.debug("turn %d: 调用 LLM (messages=%d)", turns + 1, len(messages))
                response = await self._llm.generate(
                    messages,
                    reasoning_effort=config.NOVEL_AGENT_REASONING_EFFORT,
                    model=config.NOVEL_AGENT_MODEL,
                    tools=tools_schema,
                    caller="NovelAgent",
                )

                step_tokens = response.usage.total_tokens if response.usage else 0
                _cumul_tokens += step_tokens
                logger.info("turn %d: tokens=%d cumul=%d reasoning=%d content=%d tool_calls=%d",
                            turns + 1, step_tokens, _cumul_tokens,
                            len(response.reasoning_content or ""),
                            len(response.content or ""),
                            len(response.tool_calls or []))

                await self._broadcast_sse(sse_manager, task_id, {
                    "type": "round", "turn": turns + 1, "phase": "agent",
                    "cumul_tokens": _cumul_tokens,
                })

                assistant_msg: dict = {"role": "assistant"}
                if response.content is not None:
                    assistant_msg["content"] = response.content
                if response.tool_calls:
                    assistant_msg["tool_calls"] = response.tool_calls
                    # DeepSeek 思考模式：有工具调用时必须保留 reasoning_content
                    if response.reasoning_content:
                        assistant_msg["reasoning_content"] = response.reasoning_content
                else:
                    if "content" not in assistant_msg:
                        assistant_msg["content"] = ""
                    # 无工具调用：reasoning_content 无需回传，剥离以节省上下文窗口
                messages.append(assistant_msg)

                _write_trace({
                    "turn": turns + 1, "step": "agent",
                    "agent": {"reasoning": response.reasoning_content,
                              "content": response.content,
                              "tool_calls": response.tool_calls},
                    "tokens": {"total": step_tokens},
                })

                tool_calls = response.tool_calls or []
                has_assemble = any(tc["function"]["name"] == "assemble" for tc in tool_calls)

                if has_assemble:
                    logger.info("turn %d: Agent 调用 assemble，准备退出", turns + 1)
                    for tc in tool_calls:
                        if tc["function"]["name"] == "assemble":
                            continue
                        tc_args = self._safe_parse_tool_args(tc, turns + 1)
                        if tc_args is None:
                            continue
                        await self._execute_tool(
                            tc["function"]["name"], tc_args, tc["id"],
                            work_dir, reviewer_system_prompt=reviewer_system_prompt)
                    result = await self._execute_tool(
                        "assemble", {}, "assemble_final",
                        work_dir, reviewer_system_prompt=reviewer_system_prompt)
                    _write_trace({"turn": turns + 1, "step": "tool",
                                  "tool": {"name": "assemble", "result": result}})
                    logger.info("NovelAgent 完成: %d 章, %d 字",
                                result.get("chapter_count", 0), result.get("total_chars", 0))
                    await self._broadcast_sse(sse_manager, task_id, {
                        "type": "completed",
                        "chapter_count": result.get("chapter_count", 0),
                        "total_chars": result.get("total_chars", 0),
                        "output_path": str(work_dir / result["output_path"])
                                       if result.get("output_path") else None,
                    })
                    return {
                        "output_path": str(work_dir / result["output_path"])
                                       if result.get("output_path") else None,
                        "chapter_count": result.get("chapter_count", 0),
                        "total_chars": result.get("total_chars", 0),
                    }

                if tool_calls:
                    for tc in tool_calls:
                        tc_name = tc["function"]["name"]
                        tc_args = self._safe_parse_tool_args(tc, turns + 1)
                        tc_id = tc["id"]

                        if tc_args is None:
                            messages.append({
                                "role": "tool", "tool_call_id": tc_id,
                                "content": json.dumps(
                                    {"success": False, "error": "工具参数 JSON 解析失败，请检查格式后重试。"},
                                    ensure_ascii=False)})
                            continue

                        if tc_name == "write_file" and (
                            tc_args.get("path", "").startswith("chapters/")
                            or tc_args.get("path") in ("plan.md", "state.md")
                        ):
                            path = tc_args["path"]
                            if path != _current_doc:
                                logger.info("turn %d: 文档切换 %s → %s", turns + 1,
                                            _current_doc, path)
                                _checkpoint = _temp_checkpoint.copy()
                                _current_doc = path
                                _doc_cycles = 0
                                _doc_reviews = 0
                            _doc_cycles += 1
                            result = await self._execute_tool(
                                tc_name, tc_args, tc_id,
                                work_dir, reviewer_system_prompt=reviewer_system_prompt)

                            if path.startswith("chapters/") and result.get("success"):
                                resolved = _resolve_path(work_dir, path)
                                if resolved and resolved.is_file():
                                    try:
                                        ch_text = resolved.read_text(encoding="utf-8")
                                        wc = _count_chinese_chars(ch_text)
                                    except Exception:
                                        wc = 0
                                    ch_match = re.search(r'ch_(\d+)', path)
                                    ch_idx = int(ch_match.group(1)) if ch_match else 0
                                    await self._broadcast_sse(sse_manager, task_id, {
                                        "type": "progress",
                                        "chapter_index": ch_idx,
                                        "word_count": wc, "path": path,
                                    })
                                    if path not in _chapter_progress:
                                        _chapter_progress[path] = wc
                                        await self._broadcast_sse(sse_manager, task_id, {
                                            "type": "chapter_start",
                                            "chapter_index": ch_idx, "path": path,
                                        })

                        elif tc_name == "review_chapter":
                            if _doc_reviews >= config.NOVEL_REVIEW_MAX:
                                logger.warning("turn %d: review_chapter 被拒（%d/%d）",
                                             turns + 1, _doc_reviews, config.NOVEL_REVIEW_MAX)
                                chapter_path = tc_args.get("chapter_path", "")
                                wc, cv = 0, "不适用"
                                resolved = _resolve_path(work_dir, chapter_path)
                                if resolved is not None and resolved.is_file():
                                    try:
                                        ch_text = resolved.read_text(encoding="utf-8")
                                        wc = _count_chinese_chars(ch_text)
                                        cv = _make_chars_verdict(
                                            wc, config.NOVEL_CHAPTER_MIN_CHARS,
                                            config.NOVEL_CHAPTER_MAX_CHARS)
                                    except (UnicodeDecodeError, OSError):
                                        pass
                                result = {
                                    "passed": False,
                                    "report": "不可继续审查：审核次数已达上限，请推进到下一章",
                                    "word_count": wc, "chars_verdict": cv,
                                }
                                _doc_cycles += 1
                                messages.append({
                                    "role": "tool", "tool_call_id": tc_id,
                                    "content": json.dumps(result, ensure_ascii=False)})
                                messages.append({
                                    "role": "user",
                                    "content": "不可继续审查：当前章节审核次数已达上限，请推进到下一章。"})
                                continue
                            else:
                                _doc_cycles += 1
                                _doc_reviews += 1
                                logger.info("turn %d: review_chapter %s (%d/%d)",
                                            turns + 1, tc_args.get("chapter_path"),
                                            _doc_reviews, config.NOVEL_REVIEW_MAX)
                                result = await self._execute_tool(
                                    tc_name, tc_args, tc_id,
                                    work_dir, reviewer_system_prompt=reviewer_system_prompt)

                                ch_match = re.search(r'ch_(\d+)', tc_args.get("chapter_path", ""))
                                ch_idx = int(ch_match.group(1)) if ch_match else 0
                                await self._broadcast_sse(sse_manager, task_id, {
                                    "type": "round", "turn": turns + 1, "phase": "review",
                                    "chapter_index": ch_idx,
                                    "passed": result.get("passed", False),
                                    "review_count": _doc_reviews,
                                })
                        else:
                            result = await self._execute_tool(
                                tc_name, tc_args, tc_id,
                                work_dir, reviewer_system_prompt=reviewer_system_prompt)

                        messages.append({
                            "role": "tool", "tool_call_id": tc_id,
                            "content": json.dumps(result, ensure_ascii=False)})
                        _write_trace({"turn": turns + 1, "step": "tool",
                                      "tool": {"name": tc_name, "result": result}})

                turns += 1
                _temp_checkpoint = {"messages_len": len(messages),
                                    "doc_cycles": _doc_cycles,
                                    "doc_reviews": _doc_reviews,
                                    "current_doc": _current_doc}

                if _doc_cycles >= config.NOVEL_CYCLE_MAX:
                    if _rollback_count >= config.NOVEL_ROLLBACK_MAX:
                        logger.error("turn %d: 回滚次数耗尽 (%d/%d)，退出",
                                     turns, _rollback_count, config.NOVEL_ROLLBACK_MAX)
                        await self._broadcast_sse(sse_manager, task_id, {
                            "type": "failed", "error": "回滚次数耗尽", "turn": turns})
                        return {"output_path": None, "chapter_count": 0, "total_chars": 0}

                    rollback_len = _checkpoint["messages_len"]
                    if rollback_len < 2 or rollback_len > len(messages):
                        logger.error("turn %d: 检查点无效 (%d/%d)，退出",
                                     turns, rollback_len, len(messages))
                        await self._broadcast_sse(sse_manager, task_id, {
                            "type": "failed", "error": "检查点无效", "turn": turns})
                        return {"output_path": None, "chapter_count": 0, "total_chars": 0}

                    logger.warning("turn %d: 上下文回滚 (cycle=%d/%d, rollback=%d/%d)",
                                   turns, _doc_cycles, config.NOVEL_CYCLE_MAX,
                                   _rollback_count + 1, config.NOVEL_ROLLBACK_MAX)
                    messages = messages[:rollback_len]
                    _doc_cycles = _checkpoint["doc_cycles"]
                    _doc_reviews = _checkpoint["doc_reviews"]
                    _current_doc = _checkpoint["current_doc"]
                    _temp_checkpoint = _checkpoint.copy()
                    _rollback_count += 1

            # 硬预算退出
            logger.warning("max_turns (%d) 耗尽，强制 assemble", config.NOVEL_MAX_TURNS)
            result = await self._execute_tool(
                "assemble", {}, "assemble_budget",
                work_dir, reviewer_system_prompt=reviewer_system_prompt)
            _write_trace({"step": "event", "event": "forced_termination",
                          "reason": "max_turns 耗尽"})
            logger.info("NovelAgent 完成: %d 章, %d 字 (强制退出)",
                        result.get("chapter_count", 0), result.get("total_chars", 0))
            await self._broadcast_sse(sse_manager, task_id, {
                "type": "completed",
                "chapter_count": result.get("chapter_count", 0),
                "total_chars": result.get("total_chars", 0),
                "forced": True,
            })
            return {
                "output_path": str(work_dir / result["output_path"])
                               if result.get("output_path") else None,
                "chapter_count": result.get("chapter_count", 0),
                "total_chars": result.get("total_chars", 0),
            }
        finally:
            _trace_fh.close()
