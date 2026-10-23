# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""agent_ops API 端点测试——/api/agent/* 全量领域接口（MCP 与桥接回写用）。

覆盖组：演化（时间线/关系/分支/回合收束/回收/上下文/人设）、
聊天（记忆 CRUD/检索/安全/历史/快照/消息/阶段/假流式 done）、
小说（章节读写/硬门/拼卷/任务/源读取）、通用（关怀回响）。
"""
import asyncio
import json
from uuid import uuid4

import pytest

from tests.helpers import make_characters
from tests.helpers_agent import (  # noqa: F401  isolate_db 供 client fixture 链解析
    SSECollector, assert_events, client, get_sse, isolate_db,
)


# ── 通用小工具 ──

def _sql(sql: str, params: tuple = ()) -> list[dict]:
    """在独立事件循环里执行一条 SQL（SELECT 返回行，写语句返回 []）。"""
    from server.storage.sqlite_client import get_db

    async def _run():
        db = await get_db()
        cur = await db.execute(sql, params)
        await db.commit()
        try:
            return [dict(r) for r in await cur.fetchall()]
        except Exception:
            return []

    return asyncio.run(_run())


def _login(client, nick: str) -> str:
    client.post("/api/auth/login", json={"nickname": nick})
    return nick


def _create_world(client, user_id: str) -> str:
    res = client.post("/api/worlds/create", json={
        "user_id": user_id, "name": "agent测试世界", "description": "测试",
        "world_history": "", "rules": [],
        "initial_event": {"content": "开始", "time": "黎明"},
        "characters": make_characters(3),
    })
    assert res.status_code == 201, res.text
    return res.json()["world_id"]


def _create_evolution(client, user_id: str, world_id: str) -> str:
    res = client.post("/api/evolutions/create", json={
        "user_id": user_id, "world_id": world_id,
    })
    assert res.status_code == 201, res.text
    return res.json()["evolution_id"]


def _set_evolution_state(eid: str, status: str, current_round: int,
                         max_rounds: int = 5):
    _sql("UPDATE world_evolutions SET status = ?, current_round = ?, max_rounds = ? "
         "WHERE evolution_id = ?", (status, current_round, max_rounds, eid))


def _setup_chat_prereqs(client, user_id: str) -> tuple[str, str]:
    """创建世界→演化→小说→角色行，返回 (novel_id, character_id)。"""
    from server.storage.sqlite_client import get_db, now_ms

    _login(client, user_id)
    wid = _create_world(client, user_id)

    async def _setup():
        db = await get_db()
        cursor = await db.execute(
            "SELECT character_id FROM world_characters WHERE world_id = ?", (wid,))
        row = await cursor.fetchone()
        source_cid = row["character_id"]

        eid = f"sess_{uuid4().hex[:8]}"
        nid = f"novel_{uuid4().hex[:8]}"
        now = now_ms()
        await db.execute(
            "INSERT INTO world_evolutions (evolution_id, user_id, world_id, status, "
            "current_round, created_at) VALUES (?, ?, ?, 'idle', 0, ?)",
            (eid, user_id, wid, now),
        )
        await db.execute(
            "INSERT INTO novels (novel_id, user_id, world_id, evolution_id, title, "
            "content, world_snapshot, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (nid, user_id, wid, eid, "测试小说", "内容", json.dumps({}), now),
        )
        await db.execute(
            "INSERT INTO novel_characters (character_id, novel_id, user_id, "
            "source_character_id, character_snapshot, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (f"nc_{uuid4().hex[:8]}", nid, user_id, source_cid,
             json.dumps({"name": "角色1", "identity": "测试身份"}), now),
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT character_id FROM novel_characters WHERE novel_id = ?", (nid,))
        return nid, (await cursor.fetchone())["character_id"]

    return asyncio.run(_setup())


def _create_chat(user_id: str, novel_id: str, character_id: str) -> str:
    from server.storage.sqlite_client import create_chat
    return asyncio.run(create_chat(user_id, novel_id, character_id))


def _create_novel_task(client, user_id: str) -> tuple[str, str, str]:
    """直接落库预创建 novel + processing 任务（不触发 LLM 生成）。"""
    from server.storage.sqlite_client import now_ms

    _login(client, user_id)
    wid = _create_world(client, user_id)
    eid = _create_evolution(client, user_id, wid)
    nid = f"novel_{uuid4().hex[:8]}"
    tid = f"task_{uuid4().hex[:8]}"
    now = now_ms()
    _sql(
        "INSERT INTO novels (novel_id, user_id, world_id, evolution_id, title, "
        "content, world_snapshot, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (nid, user_id, wid, eid, "测试小说", "", json.dumps({}), now),
    )
    _sql(
        "INSERT INTO novel_tasks (task_id, novel_id, evolution_id, status, created_at) "
        "VALUES (?, ?, ?, 'processing', ?)",
        (tid, nid, eid, now),
    )
    return nid, tid, eid


# ═══════════════════════════════════════════════════════════
# 演化组
# ═══════════════════════════════════════════════════════════

class TestTimelineEvent:
    def test_timeline_event_write_and_sse(self, client):
        uid = _login(client, "ao_user1")
        wid = _create_world(client, uid)
        eid = _create_evolution(client, uid, wid)

        with SSECollector(get_sse(), f"evolution:{eid}") as col:
            res = client.post(f"/api/agent/evolutions/{eid}/timeline-event", json={
                "type": "scene_setting", "content": "清晨的码头薄雾弥漫",
            })
        assert res.status_code == 200, res.text
        event = res.json()["event"]
        assert event["type"] == "scene_setting"
        assert event["content"] == "清晨的码头薄雾弥漫"
        assert event["round"] == 0

        assert_events(col, ["timeline_event"])

        # 非法类型 → 422
        res = client.post(f"/api/agent/evolutions/{eid}/timeline-event", json={
            "type": "bogus_type", "content": "非法事件",
        })
        assert res.status_code == 422

    def test_round_summary_and_relationships(self, client):
        uid = _login(client, "ao_user2")
        wid = _create_world(client, uid)
        eid = _create_evolution(client, uid, wid)

        with SSECollector(get_sse(), f"evolution:{eid}") as col:
            res = client.post(f"/api/agent/evolutions/{eid}/round-summary", json={
                "round": 1, "summary": "第一轮：众人在码头相遇",
            })
            assert res.status_code == 200
            assert res.json()["event"]["type"] == "round_summary"

            res = client.post(f"/api/agent/evolutions/{eid}/relationships", json={
                "edges": [{"from_character": "角色1", "to_character": "角色2",
                           "description": "旧识"}],
            })
            assert res.status_code == 200

        assert_events(col, ["timeline_event", "relationships"])

        # 关系已合并进 relationships JSON
        tl = client.get(
            f"/api/agent/evolutions/{eid}/timeline?since_round=0").json()
        assert tl["relationships"]["角色1"]["角色2"] == "旧识"

    def test_timeline_since_round_filter(self, client):
        uid = _login(client, "ao_user3")
        wid = _create_world(client, uid)
        eid = _create_evolution(client, uid, wid)
        client.post(f"/api/agent/evolutions/{eid}/timeline-event", json={
            "type": "action", "content": "第0轮事件"})
        _set_evolution_state(eid, "running", 1)
        client.post(f"/api/agent/evolutions/{eid}/timeline-event", json={
            "type": "action", "content": "第1轮事件"})

        res = client.get(f"/api/agent/evolutions/{eid}/timeline?since_round=1")
        assert res.status_code == 200
        data = res.json()
        assert [e["content"] for e in data["events"]] == ["第1轮事件"]
        assert data["current_round"] == 1
        assert data["max_rounds"] > 0
        assert data["status"] == "running"


class TestBranches:
    def test_push_branches_pause_sequence(self, client):
        uid = _login(client, "ao_user4")
        wid = _create_world(client, uid)
        eid = _create_evolution(client, uid, wid)
        _set_evolution_state(eid, "running", 1)

        with SSECollector(get_sse(), f"evolution:{eid}") as col:
            res = client.post(f"/api/agent/evolutions/{eid}/branches", json={
                "branches": [
                    {"title": "武力解决", "description": "直接动手"},
                    {"title": "谈判周旋", "description": "先礼后兵"},
                ],
            })
            assert res.status_code == 200, res.text

            events = col.drain()
        assert [e["type"] for e in events] == ["branches", "session_paused"]
        assert events[0]["data"]["branches"][0]["title"] == "武力解决"
        assert events[0]["data"]["branches"][0]["index"] == 0
        assert events[1]["data"]["reason"] == "conflict"

        # 状态已置 PAUSED（回合内迁移）
        tl = client.get(f"/api/agent/evolutions/{eid}/timeline").json()
        assert tl["status"] == "paused"

        # 非 RUNNING → 409
        res = client.post(f"/api/agent/evolutions/{eid}/branches", json={
            "branches": [{"title": "再推", "description": "不允许"}],
        })
        assert res.status_code == 409

    def test_pending_branches_parse(self, client):
        uid = _login(client, "ao_user5")
        wid = _create_world(client, uid)
        eid = _create_evolution(client, uid, wid)

        # 无 branch_options → null
        res = client.get(f"/api/agent/evolutions/{eid}/branches/pending")
        assert res.status_code == 200
        assert res.json()["branches"] is None

        # 第一条 branch_options（两条合格分支）
        client.post(f"/api/agent/evolutions/{eid}/timeline-event", json={
            "type": "branch_options",
            "content": json.dumps([
                {"index": 0, "title": "战", "description": "开战"},
                {"index": 1, "title": "和", "description": "议和"},
            ], ensure_ascii=False),
        })
        # 最后一条 branch_options（含一个缺 title 的元素，应被跳过）
        client.post(f"/api/agent/evolutions/{eid}/timeline-event", json={
            "type": "branch_options",
            "content": json.dumps([
                {"index": 0, "title": "甲", "description": "dA"},
                {"index": 1, "description": "缺 title 应跳过"},
                {"index": 2, "title": "丙", "description": "dC"},
            ], ensure_ascii=False),
        })

        res = client.get(f"/api/agent/evolutions/{eid}/branches/pending")
        assert res.status_code == 200
        branches = res.json()["branches"]
        # 只解析最后一条 branch_options，且缺字段元素被跳过
        assert branches == [
            {"index": 0, "title": "甲", "description": "dA"},
            {"index": 2, "title": "丙", "description": "dC"},
        ]


class TestRoundCompletion:
    def test_complete_round_waiting_then_ended(self, client):
        uid = _login(client, "ao_user6")
        wid = _create_world(client, uid)
        eid = _create_evolution(client, uid, wid)
        _set_evolution_state(eid, "running", 0, max_rounds=1)

        with SSECollector(get_sse(), f"evolution:{eid}") as col:
            res = client.post(f"/api/agent/evolutions/{eid}/complete-round")
        assert res.status_code == 200
        assert res.json() == {"status": "waiting_next_round", "round": 0}
        assert_events(col, ["round_end"])

        # 再自增 round 后 complete-round → ended + session_ended
        _set_evolution_state(eid, "running", 1, max_rounds=1)
        with SSECollector(get_sse(), f"evolution:{eid}") as col:
            res = client.post(f"/api/agent/evolutions/{eid}/complete-round")
        assert res.status_code == 200
        assert res.json() == {"status": "ended", "round": 1}
        assert_events(col, ["session_ended"])

    def test_recover_running_to_waiting(self, client):
        uid = _login(client, "ao_user7")
        wid = _create_world(client, uid)
        eid = _create_evolution(client, uid, wid)
        _set_evolution_state(eid, "running", 3, max_rounds=5)

        with SSECollector(get_sse(), f"evolution:{eid}") as col:
            res = client.post(f"/api/agent/evolutions/{eid}/recover", json={
                "reason": "导演会话超时",
            })
        assert res.status_code == 200
        assert res.json() == {"status": "waiting_next_round", "round": 3}

        events = col.drain()
        assert [e["type"] for e in events] == ["error", "round_end"]
        assert events[0]["data"]["message"] == "导演会话超时"

        # 重复 recover 幂等——直接返回现状，无新 SSE
        with SSECollector(get_sse(), f"evolution:{eid}") as col:
            res = client.post(f"/api/agent/evolutions/{eid}/recover", json={
                "reason": "再次回收",
            })
        assert res.status_code == 200
        assert res.json() == {"status": "waiting_next_round", "round": 3}
        assert_events(col, [])


class TestCharacterContextAndProfile:
    def test_context_get_append_and_profile(self, client):
        uid = _login(client, "ao_user8")
        wid = _create_world(client, uid)
        eid = _create_evolution(client, uid, wid)

        # GET 初始上下文（纯领域服务：create() 不再预置 system 模板消息，镜像列初始为空）
        res = client.get(
            f"/api/agent/evolutions/{eid}/characters/角色1/context")
        assert res.status_code == 200
        initial = res.json()["messages"]
        assert initial == []

        # POST 追加 system 消息并持久化
        res = client.post(
            f"/api/agent/evolutions/{eid}/characters/角色1/context",
            json={"message": "我的记忆：今天捡到一把钥匙"})
        assert res.status_code == 200
        assert res.json()["messages"][-1] == {
            "role": "system", "content": "我的记忆：今天捡到一把钥匙"}

        # 再 GET 确认持久化
        res = client.get(
            f"/api/agent/evolutions/{eid}/characters/角色1/context")
        assert res.json()["messages"][-1]["content"] == "我的记忆：今天捡到一把钥匙"

        # 人设 = world_characters 行全字段
        res = client.get(f"/api/agent/evolutions/{eid}/characters/角色1/profile")
        assert res.status_code == 200
        char = res.json()["character"]
        assert char["name"] == "角色1"
        assert char["identity"] == "测试身份"
        assert "accent_color" in char

        # 不存在的角色 → 404
        res = client.get(
            f"/api/agent/evolutions/{eid}/characters/路人甲/profile")
        assert res.status_code == 404


class TestWorldConfig:
    def test_world_config_and_meta_404(self, client):
        uid = _login(client, "ao_user9")
        wid = _create_world(client, uid)
        eid = _create_evolution(client, uid, wid)

        res = client.get(f"/api/agent/evolutions/{eid}/world-config")
        assert res.status_code == 200
        data = res.json()
        assert data["world_config"]["name"] == "agent测试世界"
        assert len(data["characters"]) == 3

        # 软删世界后 world-config 仍 200（meta 级查询，不抛 TypeError）
        _sql("UPDATE worlds SET is_deleted = 1 WHERE world_id = ?", (wid,))
        res = client.get(f"/api/agent/evolutions/{eid}/world-config")
        assert res.status_code == 200
        assert len(res.json()["characters"]) == 3

    def test_meta_existence_404(self, client):
        uid = _login(client, "ao_user10")
        wid = _create_world(client, uid)
        eid = _create_evolution(client, uid, wid)
        novel_id, character_id = _setup_chat_prereqs(client, "ao_user10b")
        cid = _create_chat("ao_user10b", novel_id, character_id)
        nid, tid, _ = _create_novel_task(client, "ao_user10c")

        # 不存在的 eid / cid / tid / mid / ncid / nid → 404 且 detail 中文
        res = client.get("/api/agent/evolutions/no-such-eid/world-config")
        assert res.status_code == 404
        assert "不存在" in res.json()["detail"]

        res = client.post("/api/agent/chats/no-such-cid/stage",
                          json={"stage": "thinking"})
        assert res.status_code == 404
        assert "不存在" in res.json()["detail"]

        res = client.get("/api/agent/novel-tasks/no-such-tid")
        assert res.status_code == 404
        assert "不存在" in res.json()["detail"]

        res = client.patch("/api/agent/memories/no-such-mid", json={"content": "x"})
        assert res.status_code == 404
        assert "不存在" in res.json()["detail"]

        res = client.get("/api/agent/novel-characters/no-such-ncid/snapshot")
        assert res.status_code == 404
        assert "不存在" in res.json()["detail"]

        res = client.get("/api/agent/novels/no-such-nid/text")
        assert res.status_code == 404
        assert "不存在" in res.json()["detail"]

        # 合法资源路径冒烟（上面创建的都可达）
        assert client.get(
            f"/api/agent/evolutions/{eid}/world-config").status_code == 200
        assert client.get(f"/api/agent/chats/{cid}/history").status_code == 200
        assert client.get(f"/api/agent/novel-tasks/{tid}").status_code == 200


# ═══════════════════════════════════════════════════════════
# 聊天组
# ═══════════════════════════════════════════════════════════

class TestMemories:
    def test_memory_crud_and_capacity(self, client, monkeypatch):
        import server.config as cfg
        uid = "ao_mem_user"
        novel_id, character_id = _setup_chat_prereqs(client, uid)
        monkeypatch.setattr(cfg.config, "MEMORY_LIMIT", 2)

        # write
        res = client.post("/api/agent/memories", json={
            "user_id": uid, "novel_id": novel_id, "character_id": character_id,
            "content": "用户喜欢在雨天喝咖啡", "type": "user_fact", "importance": 0.8,
        })
        assert res.status_code == 200, res.text
        mid1 = res.json()["memory"]["memory_id"]
        assert res.json()["memory"]["content"] == "用户喜欢在雨天喝咖啡"

        res = client.post("/api/agent/memories", json={
            "user_id": uid, "novel_id": novel_id, "character_id": character_id,
            "content": "用户养了一只猫", "type": "event",
        })
        assert res.status_code == 200
        mid2 = res.json()["memory"]["memory_id"]

        # 容量满（MEMORY_LIMIT=2）→ 第三条 409
        res = client.post("/api/agent/memories", json={
            "user_id": uid, "novel_id": novel_id, "character_id": character_id,
            "content": "第三条记忆", "type": "event",
        })
        assert res.status_code == 409
        assert "记忆容量已满" in res.json()["detail"]

        # user-facts 过滤：只返回 user_fact 类型
        res = client.get(
            f"/api/agent/memories/user-facts?user_id={uid}&novel_id={novel_id}")
        assert res.status_code == 200
        facts = res.json()["memories"]
        assert len(facts) == 1
        assert facts[0]["memory_id"] == mid1
        assert facts[0]["type"] == "user_fact"

        # retrieve 命中（BM25 关键词重叠）
        res = client.post("/api/agent/memories/retrieve", json={
            "user_id": uid, "novel_id": novel_id,
            "character_id": character_id, "query": "雨天 咖啡",
        })
        assert res.status_code == 200
        memories = res.json()["memories"]
        assert len(memories) >= 1
        assert memories[0]["memory_id"] == mid1

        # update
        res = client.patch(f"/api/agent/memories/{mid1}", json={
            "content": "用户喜欢在晴天喝茶"})
        assert res.status_code == 200
        assert res.json()["memory"]["content"] == "用户喜欢在晴天喝茶"

        # delete
        res = client.delete(f"/api/agent/memories/{mid2}")
        assert res.status_code == 200
        assert res.json()["ok"] is True

        res = client.get(
            f"/api/agent/memories/user-facts?user_id={uid}&novel_id={novel_id}")
        assert len(res.json()["memories"]) == 1
        assert res.json()["memories"][0]["content"] == "用户喜欢在晴天喝茶"


class TestChatFlow:
    def test_chat_stage_and_done_stream(self, client):
        uid = "ao_chat_user"
        novel_id, character_id = _setup_chat_prereqs(client, uid)
        cid = _create_chat(uid, novel_id, character_id)

        with SSECollector(get_sse(), f"chat:{cid}") as col:
            # 阶段事件
            res = client.post(f"/api/agent/chats/{cid}/stage",
                              json={"stage": "thinking"})
            assert res.status_code == 200
            assert_events(col, ["thinking"])

            # 非法阶段 → 422
            res = client.post(f"/api/agent/chats/{cid}/stage",
                              json={"stage": "bogus"})
            assert res.status_code == 422

            # done：假流式 token + 落库
            text = "你好，今天天气不错。"
            res = client.post(f"/api/agent/chats/{cid}/done", json={
                "character_message": {"content": text}})
            assert res.status_code == 200, res.text

            events = col.drain()
        types = [e.get("event") for e in events]
        assert types[-1] == "done"
        assert all(t == "token" for t in types[:-1]) and len(types) > 1

        # token 序列拼接 == 原文
        streamed = "".join(e["data"]["content"] for e in events if e["event"] == "token")
        assert streamed == text

        # done 事件含持久化 message
        done_data = events[-1]["data"]
        assert done_data["chat_id"] == cid
        assert done_data["message"]["role"] == "character"
        assert done_data["message"]["content"] == text

        # messages 落库
        res = client.get(f"/api/agent/chats/{cid}/history?last_n=20")
        assert res.status_code == 200
        messages = res.json()["messages"]
        assert messages[-1]["role"] == "character"
        assert messages[-1]["content"] == text

    def test_chat_append_message_and_history(self, client):
        uid = "ao_chat_user2"
        novel_id, character_id = _setup_chat_prereqs(client, uid)
        cid = _create_chat(uid, novel_id, character_id)

        res = client.post(f"/api/agent/chats/{cid}/messages", json={
            "message": {"role": "user", "content": "你好呀"}})
        assert res.status_code == 200

        res = client.get(f"/api/agent/chats/{cid}/history?last_n=20")
        assert res.status_code == 200
        messages = res.json()["messages"]
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "你好呀"
        assert "timestamp" in messages[-1]

    def test_character_snapshot(self, client):
        uid = "ao_chat_user3"
        novel_id, character_id = _setup_chat_prereqs(client, uid)

        res = client.get(f"/api/agent/novel-characters/{character_id}/snapshot")
        assert res.status_code == 200
        assert res.json()["snapshot"]["name"] == "角色1"


class TestSafety:
    def test_extreme_emotion(self, client):
        uid = "ao_safety_user"
        novel_id, character_id = _setup_chat_prereqs(client, uid)

        res = client.post("/api/agent/safety/extreme-emotion", json={
            "user_id": uid, "novel_id": novel_id,
            "character_id": character_id,
            "summary": "用户表达了极端情绪", "level": 0.9,
        })
        assert res.status_code == 200
        assert res.json()["ok"] is True


# ═══════════════════════════════════════════════════════════
# 小说组
# ═══════════════════════════════════════════════════════════

class TestPrecheck:
    def test_precheck_hard_gate(self, client, monkeypatch, tmp_path):
        import server.config as cfg
        monkeypatch.setattr(cfg.config, "NOVEL_CHAPTER_MIN_CHARS", 10)
        monkeypatch.setattr(cfg.config, "NOVEL_CHAPTER_MAX_CHARS", 100)
        monkeypatch.setattr(cfg.config, "NOVEL_WORK_DIR_BASE", str(tmp_path / "work"))

        nid, tid, _ = _create_novel_task(client, "ao_novel_user1")

        # 短文本 → 字数 issue
        res = client.post(f"/api/agent/novel-tasks/{tid}/chapters", json={
            "index": 1, "title": "第一章", "content": "太短了。"})
        assert res.status_code == 200
        res = client.post(f"/api/agent/novel-tasks/{tid}/precheck", json={"index": 1})
        assert res.status_code == 200
        data = res.json()
        assert data["passed"] is False
        assert any("字数" in issue for issue in data["issues"])

        # 含 --- 残留 → issue（字数达标）
        text_with_dash = "这是一段足够长的正文内容，用于测试硬门检查逻辑。\n---\n继续写下去，确保字数达标即可。"
        client.post(f"/api/agent/novel-tasks/{tid}/chapters", json={
            "index": 2, "title": "第二章", "content": text_with_dash})
        res = client.post(f"/api/agent/novel-tasks/{tid}/precheck", json={"index": 2})
        data = res.json()
        assert data["passed"] is False
        assert any("---" in issue for issue in data["issues"])

        # 达标文本 → passed=true
        good_text = "这是一个完全达标的章节正文，没有任何违规标记与残留符号。"
        res = client.post(f"/api/agent/novel-tasks/{tid}/chapters", json={
            "index": 3, "title": "第三章", "content": good_text})
        assert res.status_code == 200
        res = client.post(f"/api/agent/novel-tasks/{tid}/precheck", json={"index": 3})
        assert res.status_code == 200
        data = res.json()
        assert data["passed"] is True
        assert data["issues"] == []

        # 读回章节内容一致
        res = client.get(f"/api/agent/novel-tasks/{tid}/chapters/3")
        assert res.status_code == 200
        assert good_text in res.json()["content"]


class TestAssemble:
    def test_assemble_creates_novel_and_completes(self, client, monkeypatch, tmp_path):
        import server.config as cfg
        monkeypatch.setattr(cfg.config, "NOVEL_WORK_DIR_BASE", str(tmp_path / "work"))

        nid, tid, _ = _create_novel_task(client, "ao_novel_user2")

        ch1 = "清晨的雾气笼罩着小镇，街道上空无一人，只有脚步声渐近。"
        ch2 = "夜幕终于降临，灯火渐次亮起，人声与杯盏声交织成潮。"
        assert client.post(f"/api/agent/novel-tasks/{tid}/chapters", json={
            "index": 1, "title": "第一章", "content": ch1}).status_code == 200
        assert client.post(f"/api/agent/novel-tasks/{tid}/chapters", json={
            "index": 2, "title": "第二章", "content": ch2}).status_code == 200

        with SSECollector(get_sse(), f"novel:{tid}") as col:
            res = client.post(f"/api/agent/novel-tasks/{tid}/assemble")
        assert res.status_code == 200, res.text
        assert res.json() == {"novel_id": nid, "status": "completed"}
        assert_events(col, ["completed"])

        # 任务 completed
        res = client.get(f"/api/agent/novel-tasks/{tid}")
        assert res.status_code == 200
        assert res.json()["task"]["status"] == "completed"

        # novels 行已写入全文 + world_snapshot
        rows = _sql("SELECT content, world_snapshot FROM novels WHERE novel_id = ?",
                    (nid,))
        assert len(rows) == 1
        content = rows[0]["content"]
        assert ch1 in content and ch2 in content
        assert "全篇完" in content
        assert "# 第1章" in content and "# 第2章" in content
        snapshot = json.loads(rows[0]["world_snapshot"])
        assert snapshot["name"] == "agent测试世界"


class TestTaskAndSource:
    def test_task_fail(self, client, monkeypatch, tmp_path):
        import server.config as cfg
        monkeypatch.setattr(cfg.config, "NOVEL_WORK_DIR_BASE", str(tmp_path / "work"))
        nid, tid, _ = _create_novel_task(client, "ao_novel_user3")

        with SSECollector(get_sse(), f"novel:{tid}") as col:
            res = client.post(f"/api/agent/novel-tasks/{tid}/fail", json={
                "reason": "审查重写上限耗尽"})
        assert res.status_code == 200
        assert res.json()["ok"] is True
        assert_events(col, ["error"])

        res = client.get(f"/api/agent/novel-tasks/{tid}")
        task = res.json()["task"]
        assert task["status"] == "failed"
        assert task["error"] == "审查重写上限耗尽"

    def test_novel_source_and_text(self, client):
        uid = "ao_novel_user4"
        novel_id, character_id = _setup_chat_prereqs(client, uid)

        # source：演化记录 + world 快照 + 角色（写作/提取种子）
        res = client.get(f"/api/agent/novels/{novel_id}/source")
        assert res.status_code == 200
        source = res.json()
        assert source["timeline"] == []
        assert source["world_snapshot"]["name"] == "agent测试世界"
        assert len(source["characters"]) == 3

        # text：已生成全文
        res = client.get(f"/api/agent/novels/{novel_id}/text")
        assert res.status_code == 200
        assert res.json()["content"] == "内容"


# ═══════════════════════════════════════════════════════════
# 通用
# ═══════════════════════════════════════════════════════════

class TestCareEcho:
    def test_task_fail_and_care_echo(self, client):
        uid = "ao_care_user"
        novel_id, character_id = _setup_chat_prereqs(client, uid)

        # care_level=0 → 概率必不命中 → message 为 null
        _sql("INSERT OR REPLACE INTO care_settings (user_id, novel_id, character_id, "
             "level) VALUES (?, ?, ?, 0)", (uid, novel_id, character_id))
        res = client.post("/api/agent/care/echo", json={
            "user_id": uid, "novel_id": novel_id, "character_id": character_id,
        })
        assert res.status_code == 200
        assert res.json()["message"] is None

        # 资源不存在 → 404
        res = client.post("/api/agent/care/echo", json={
            "user_id": uid, "novel_id": novel_id,
            "character_id": "no-such-char"})
        assert res.status_code == 404
