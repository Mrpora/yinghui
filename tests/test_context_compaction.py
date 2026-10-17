# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""导演上下文压缩保险丝测试（决策 D6）。"""
import asyncio

import pytest


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("SQLITE_PATH", db_path)
    monkeypatch.setenv("LLM_API_KEY", "sk-test-compact")

    import server.config as cfg
    monkeypatch.setattr(cfg.config, "SQLITE_PATH", db_path)

    import server.storage.sqlite_client as sc
    sc._conn = None
    asyncio.run(sc.init_db())

    import server.prompt_loader as pl
    pl.PROMPTS = {
        "evolution_agent/director_system": "导演提示词 {world_name} {world_config}",
        "evolution_agent/character_system": "角色提示词 {character_name} {identity} "
            "{personality} {speech_style} {world_name} {world_description} "
            "{world_history} {world_rules} {world_knowledge} {attitude_block} "
            "{core_goal} {backstory}",
    }

    yield

    if sc._conn:
        asyncio.run(sc._conn.close())
        sc._conn = None


def _make_orchestrator(monkeypatch, threshold: int):
    import server.config as cfg
    import server.ai.evolution_agent.agent as agent_mod
    # 同时补丁当前单例与 agent 模块持有的引用：全量回归时 test_config.py 的
    # reload 会替换 server.config.config，而 agent.py 仍持有最初导入的 Config 对象
    monkeypatch.setattr(cfg.config, "EVOLUTION_COMPACT_THRESHOLD_CHARS", threshold)
    monkeypatch.setattr(agent_mod.config, "EVOLUTION_COMPACT_THRESHOLD_CHARS", threshold)
    from server.ai.common.llm_client import LLMClient
    from server.ai.evolution_agent.agent import PipelineOrchestrator
    from server.services.session_manager import SessionManager
    from server.sse.sse_manager import SSEManager
    return PipelineOrchestrator(LLMClient(cfg.config), SessionManager(), SSEManager())


def _build_session(monkeypatch):
    """创建 3 人世界与演化会话，返回 (mgr, session)。"""
    from server.storage.sqlite_client import upsert_user, create_world
    from server.services.session_manager import SessionManager

    async def _create():
        await upsert_user("compact_user")
        wid = await create_world(
            "compact_user", "压缩世界", "描述", "历史", ["规则1"],
            {"content": "开始", "time": "黎明"},
            [{"name": "角色1", "identity": "剑客", "attitudes": {"角色2": "信任"}},
             {"name": "角色2", "identity": "医师", "attitudes": {"角色1": "怀疑"}},
             {"name": "角色3", "identity": "商人", "attitudes": {}}],
        )
        mgr = SessionManager()
        session = await mgr.create("compact_user", wid)
        return mgr, session

    return asyncio.run(_create())


def _fake_rounds(session, rounds: int, filler: str = "x" * 200):
    """向导演上下文注入 rounds 轮假消息，每轮 3 条（步骤指令 + 助手 + 工具结果）。"""
    for r in range(1, rounds + 1):
        session.director_context.append(
            {"role": "user", "content": f"[第 {r} 轮] 步骤0：冲突潜质扫描。\n{filler}"})
        session.director_context.append(
            {"role": "assistant", "content": f"第 {r} 轮分析结论 {filler}"})
        session.director_context.append(
            {"role": "user", "content": f"[第 {r} 轮] 步骤1：场景设定。\n{filler}"})


def _seed_summaries(mgr, session_id: str, rounds: int):
    for r in range(1, rounds + 1):
        asyncio.run(mgr.append_timeline_event(session_id, {
            "type": "round_summary", "round": r, "content": f"第 {r} 轮官方摘要",
        }))


class TestContextCompaction:

    def test_compaction_triggers_and_rebuilds(self, monkeypatch):
        mgr, session = _build_session(monkeypatch)
        _fake_rounds(session, rounds=4)          # 当前 round 将设为 5
        _seed_summaries(mgr, session.id, rounds=4)
        session.current_round = 5
        size_before = sum(len(str(m.get("content") or "")) for m in session.director_context)
        assert size_before >= 2400

        orch = _make_orchestrator(monkeypatch, threshold=1000)   # 阈值调低强制触发
        asyncio.run(orch._maybe_compact_director_context(session))

        ctx = session.director_context
        assert ctx[0]["role"] == "system"                       # system 保留
        assert ctx[1]["role"] == "user"
        assert ctx[1]["content"].startswith("[历史压缩]")
        assert "第 1 轮官方摘要" in ctx[1]["content"] and "第 2 轮官方摘要" in ctx[1]["content"]
        joined = "".join(str(m.get("content") or "") for m in ctx)
        assert "[第 1 轮]" not in joined                         # 第 1-2 轮原文已进摘要
        assert "[第 2 轮]" not in joined
        assert "[第 3 轮]" in joined and "[第 4 轮]" in joined   # 最近两轮原文保留
        size_after = sum(len(str(m.get("content") or "")) for m in ctx)
        assert size_after < size_before

    def test_compaction_not_triggered_below_threshold(self, monkeypatch):
        mgr, session = _build_session(monkeypatch)
        _fake_rounds(session, rounds=2)
        session.current_round = 3
        orch = _make_orchestrator(monkeypatch, threshold=10 ** 9)
        before = [dict(m) for m in session.director_context]
        asyncio.run(orch._maybe_compact_director_context(session))
        assert session.director_context == before
