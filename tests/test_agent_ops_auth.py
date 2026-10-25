# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""agent_ops 鉴权测试——AGENT_TOKEN 横切依赖（debt-wave3 W1）。

设 token：无头 401 / 错头 401 / 对头 200；未设（默认空）：开放如旧。
鉴权在 router 级 dependency 一处声明，此处以 GET 端点为主断言，
另以一条 POST 端点佐证全路由生效（依赖先于端点与 body 校验触发）。
"""
import asyncio
import json

import pytest

from tests.helpers import make_characters
from tests.helpers_agent import client, isolate_db  # noqa: F401  fixture 链

_NOVEL_ID = "novel_authtest"


@pytest.fixture
def set_agent_token(monkeypatch):
    """把 config.AGENT_TOKEN 设为测试令牌（依赖每次请求动态读取）。"""
    import server.config as cfg
    monkeypatch.setattr(cfg.config, "AGENT_TOKEN", "test-shared-token")


@pytest.fixture
def seed_novel(client):
    """造一条真实 novels 行（登录 + 建世界 + SQL 直插，FK 合法），user-facts 200 用。"""
    from server.storage.sqlite_client import get_db, now_ms

    client.post("/api/auth/login", json={"nickname": "u1"})
    res = client.post("/api/worlds/create", json={
        "user_id": "u1", "name": "鉴权测试世界", "description": "测试",
        "world_history": "", "rules": [],
        "initial_event": {"content": "开始", "time": "黎明"},
        "characters": make_characters(3),
    })
    assert res.status_code == 201, res.text
    world_id = res.json()["world_id"]
    res = client.post("/api/evolutions/create", json={
        "user_id": "u1", "world_id": world_id})
    assert res.status_code == 201, res.text
    evolution_id = res.json()["evolution_id"]

    async def _insert():
        db = await get_db()
        await db.execute(
            "INSERT INTO novels (novel_id, user_id, world_id, evolution_id, title, "
            "content, world_snapshot, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (_NOVEL_ID, "u1", world_id, evolution_id, "测试小说", "内容",
             json.dumps({}), now_ms()))
        await db.commit()

    asyncio.run(_insert())


def _user_facts_url() -> str:
    return f"/api/agent/memories/user-facts?user_id=u1&novel_id={_NOVEL_ID}"


def test_default_open_without_token(client, seed_novel, monkeypatch):
    """未设 AGENT_TOKEN（默认空）→ 无头 200（开放如旧，零配置行为不变）。"""
    import server.config as cfg
    monkeypatch.setattr(cfg.config, "AGENT_TOKEN", "")
    res = client.get(_user_facts_url())
    assert res.status_code == 200
    assert res.json() == {"memories": []}


def test_token_set_missing_header_401(client, seed_novel, set_agent_token):
    res = client.get(_user_facts_url())
    assert res.status_code == 401
    assert "X-Agent-Token" in res.json()["detail"]  # 中文 detail 指明缺失的请求头


def test_token_set_wrong_header_401(client, seed_novel, set_agent_token):
    res = client.get(_user_facts_url(), headers={"X-Agent-Token": "wrong-token"})
    assert res.status_code == 401
    assert "X-Agent-Token" in res.json()["detail"]


def test_wrong_token_via_constant_time_compare(client, seed_novel, set_agent_token,
                                               monkeypatch):
    """错 token 仍 401，且失配判定走 secrets.compare_digest（W4a F1）。

    行为与旧 `!=` 完全一致（401），此处以 spy 锁定实现路径：鉴权必须经过
    恒时比较，防止回归为可计时侧信道的直接字符串比较。
    """
    import secrets as _secrets

    import server.routers.agent_ops as agent_ops_mod

    calls: list[tuple[str, str]] = []
    _real_compare = _secrets.compare_digest

    def _spy(a: str, b: str) -> bool:
        calls.append((a, b))
        return _real_compare(a, b)

    monkeypatch.setattr(agent_ops_mod.secrets, "compare_digest", _spy)
    res = client.get(_user_facts_url(), headers={"X-Agent-Token": "wrong-token"})
    assert res.status_code == 401
    assert "X-Agent-Token" in res.json()["detail"]
    assert calls == [("wrong-token", "test-shared-token")]


def test_token_set_correct_header_200(client, seed_novel, set_agent_token):
    res = client.get(_user_facts_url(), headers={"X-Agent-Token": "test-shared-token"})
    assert res.status_code == 200
    assert res.json() == {"memories": []}


def test_token_applies_router_wide_post(client, set_agent_token):
    """router 级 dependency 覆盖全部 /api/agent/* 路由（POST 端点同样拦截）。"""
    res = client.post("/api/agent/memories")  # 无头且无 body → 鉴权先于 body 校验
    assert res.status_code == 401
    assert "X-Agent-Token" in res.json()["detail"]
