# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Prompt 加载器测试——预加载、缓存命中/未命中。"""
import pytest
from pathlib import Path


class TestPreloadPrompts:
    def test_loads_md_files_from_directory(self, tmp_path):
        """从目录加载 .md 文件，key 为相对路径（不含 .md）。"""
        sub = tmp_path / "evolution_agent"
        sub.mkdir()
        (sub / "director_system.md").write_text("你是导演", encoding="utf-8")
        (sub / "character_system.md").write_text("你是角色", encoding="utf-8")

        from server.prompt_loader import preload_prompts
        prompts = preload_prompts(str(tmp_path))

        assert "evolution_agent/director_system" in prompts
        assert prompts["evolution_agent/director_system"] == "你是导演"
        assert prompts["evolution_agent/character_system"] == "你是角色"

    def test_ignores_non_md_files(self, tmp_path):
        """跳过非 .md 文件。"""
        (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")

        from server.prompt_loader import preload_prompts
        prompts = preload_prompts(str(tmp_path))

        assert "notes" not in prompts

    def test_empty_directory(self, tmp_path):
        """空目录应返回空 dict。"""
        from server.prompt_loader import preload_prompts, PROMPTS
        PROMPTS.clear()
        prompts = preload_prompts(str(tmp_path))
        assert prompts == {}

    def test_nested_directories(self, tmp_path):
        """嵌套目录下 .md 文件 key 包含子目录路径。"""
        sub = tmp_path / "evolution_agent_v2"
        sub.mkdir()
        (sub / "world_injection.md").write_text("世界配置注入", encoding="utf-8")

        from server.prompt_loader import preload_prompts
        prompts = preload_prompts(str(tmp_path))

        assert "evolution_agent_v2/world_injection" in prompts


class TestGetPrompt:
    def test_returns_cached_prompt(self, tmp_path):
        """get_prompt 从全局缓存读取。"""
        (tmp_path / "test_prompt.md").write_text("缓存内容", encoding="utf-8")

        from server.prompt_loader import preload_prompts, get_prompt
        preload_prompts(str(tmp_path))

        assert get_prompt("test_prompt") == "缓存内容"

    def test_returns_empty_for_missing_key(self):
        """不存在的 key 返回空字符串。"""
        from server.prompt_loader import get_prompt
        assert get_prompt("nonexistent_key") == ""
