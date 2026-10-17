# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""世界补全服务测试——{character_count} 注入。"""
import asyncio
import json


def test_smart_complete_world_injects_character_count(monkeypatch):
    import server.ai.completer_llm.completer as comp

    captured: dict = {}

    class _FakeResp:
        content = json.dumps({
            "world_history": "历史",
            "rules": ["规则一", "规则二", "规则三"],
            "initial_event": {"content": "事件", "time": "元年"},
            "characters": [
                {"name": f"角色{i}", "identity": "女，侠客", "personality": "沉静",
                 "speech_style": "简短", "goal": "复仇", "backstory": "往事",
                 "initial_location": "渡口", "initial_state": "待命", "attitudes": {}}
                for i in range(1, 6)
            ],
        }, ensure_ascii=False)

    class _FakeLLM:
        async def generate(self, messages, **kwargs):
            captured["system"] = messages[0]["content"]
            captured["user"] = messages[1]["content"]
            return _FakeResp()

    monkeypatch.setattr(comp, "_llm", _FakeLLM())
    monkeypatch.setattr(comp, "get_prompt", lambda _key: "N={character_count}")

    world_data = {"name": "测试", "description": "描述",
                  "characters": [{"name": f"已有{i}", "identity": "侠"} for i in range(1, 6)]}
    result = asyncio.run(comp.smart_complete_world(world_data, character_count=5))

    assert captured["system"] == "N=5"                       # 占位符已替换、无残留
    assert "5 个角色" in captured["user"]                    # user prompt 首行声明
    assert len(result["characters"]) == 5
