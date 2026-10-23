# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Config 配置类测试——环境变量加载、默认值、类型校验。"""
import os
import pytest
from server.config import _int_env, _float_env, _list_env


class TestIntEnv:
    def test_returns_default_when_not_set(self, monkeypatch):
        monkeypatch.delenv("TEST_INT_KEY", raising=False)
        assert _int_env("TEST_INT_KEY", 42) == 42

    def test_parses_valid_int(self, monkeypatch):
        monkeypatch.setenv("TEST_INT_KEY", "100")
        assert _int_env("TEST_INT_KEY", 0) == 100

    def test_raises_on_invalid_int(self, monkeypatch):
        monkeypatch.setenv("TEST_INT_KEY", "abc")
        with pytest.raises(ValueError, match="不是有效整数"):
            _int_env("TEST_INT_KEY", 0)

    def test_parses_zero(self, monkeypatch):
        monkeypatch.setenv("TEST_INT_KEY", "0")
        assert _int_env("TEST_INT_KEY", 10) == 0

    def test_parses_negative(self, monkeypatch):
        monkeypatch.setenv("TEST_INT_KEY", "-5")
        assert _int_env("TEST_INT_KEY", 10) == -5


class TestFloatEnv:
    def test_returns_default_when_not_set(self, monkeypatch):
        monkeypatch.delenv("TEST_FLOAT_KEY", raising=False)
        assert _float_env("TEST_FLOAT_KEY", 3.14) == 3.14

    def test_parses_valid_float(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT_KEY", "0.75")
        assert _float_env("TEST_FLOAT_KEY", 0.0) == 0.75

    def test_raises_on_invalid_float(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT_KEY", "not-a-number")
        with pytest.raises(ValueError, match="不是有效浮点数"):
            _float_env("TEST_FLOAT_KEY", 0.0)

    def test_parses_negative_float(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT_KEY", "-2.5")
        assert _float_env("TEST_FLOAT_KEY", 0.0) == -2.5


class TestListEnv:
    def test_returns_default_when_not_set(self, monkeypatch):
        monkeypatch.delenv("TEST_LIST_KEY", raising=False)
        assert _list_env("TEST_LIST_KEY", ["a", "b"]) == ["a", "b"]

    def test_returns_default_when_empty_string(self, monkeypatch):
        monkeypatch.setenv("TEST_LIST_KEY", "")
        assert _list_env("TEST_LIST_KEY", ["default"]) == ["default"]

    def test_parses_comma_separated_list(self, monkeypatch):
        monkeypatch.setenv("TEST_LIST_KEY", "a, b, c")
        assert _list_env("TEST_LIST_KEY", []) == ["a", "b", "c"]

    def test_strips_whitespace(self, monkeypatch):
        monkeypatch.setenv("TEST_LIST_KEY", "  x  ,  y  ")
        assert _list_env("TEST_LIST_KEY", []) == ["x", "y"]

    def test_filters_empty_items(self, monkeypatch):
        monkeypatch.setenv("TEST_LIST_KEY", "a,,b,")
        assert _list_env("TEST_LIST_KEY", []) == ["a", "b"]


class TestConfigDefaults:
    """验证 Config 对象的默认值与 env 覆盖。"""

    def test_config_loads_defaults(self, monkeypatch):
        # load_dotenv 不会覆盖已有环境变量，setenv 后 reload 即可隔离 .env
        monkeypatch.setenv("INSTANT_MEMORY_SIZE", "200")
        monkeypatch.setenv("EVOLUTION_DEFAULT_ROUNDS", "20")
        monkeypatch.setenv("MEMORY_LIMIT", "10")
        monkeypatch.setenv("CARE_COOLDOWN_HOURS", "24")
        monkeypatch.setenv("DECAY_HALF_LIFE_DAYS", "15.0")
        monkeypatch.setenv("NOVEL_CHAPTER_MIN_CHARS", "3000")
        monkeypatch.setenv("NOVEL_CHAPTER_MAX_CHARS", "5000")
        monkeypatch.setenv("EMBEDDING_DIM", "1024")
        monkeypatch.setenv("BRIDGE_URL", "http://127.0.0.1:8100")

        from importlib import reload
        import server.config
        reload(server.config)
        c = server.config.Config()
        assert c.EVOLUTION_DEFAULT_ROUNDS == 20
        assert c.MEMORY_LIMIT == 10
        assert c.INSTANT_MEMORY_SIZE == 200
        assert c.CARE_COOLDOWN_HOURS == 24
        assert c.DECAY_HALF_LIFE_DAYS == 15.0
        assert c.NOVEL_CHAPTER_MIN_CHARS == 3000
        assert c.NOVEL_CHAPTER_MAX_CHARS == 5000
        assert c.EMBEDDING_DIM == 1024
        assert c.BRIDGE_URL == "http://127.0.0.1:8100"

    def test_config_bridge_url_default(self, monkeypatch):
        """未设置 BRIDGE_URL 时默认指向本机 8100。"""
        monkeypatch.delenv("BRIDGE_URL", raising=False)
        from importlib import reload
        import server.config
        reload(server.config)
        c = server.config.Config()
        assert c.BRIDGE_URL == "http://127.0.0.1:8100"

    def test_config_env_overrides(self, monkeypatch):
        monkeypatch.setenv("EVOLUTION_DEFAULT_ROUNDS", "10")
        monkeypatch.setenv("MEMORY_LIMIT", "5")
        monkeypatch.setenv("BRIDGE_URL", "http://127.0.0.1:9000")
        from importlib import reload
        import server.config
        reload(server.config)
        c = server.config.Config()
        assert c.EVOLUTION_DEFAULT_ROUNDS == 10
        assert c.MEMORY_LIMIT == 5
        assert c.BRIDGE_URL == "http://127.0.0.1:9000"

    def test_config_max_rounds(self, monkeypatch):
        from importlib import reload
        import server.config
        reload(server.config)
        c = server.config.Config()
        assert c.EVOLUTION_MAX_ROUNDS == 100

        monkeypatch.setenv("EVOLUTION_MAX_ROUNDS", "30")
        reload(server.config)
        c = server.config.Config()
        assert c.EVOLUTION_MAX_ROUNDS == 30
