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
    """验证 Config 对象在模拟 API key 后的默认值。"""

    @pytest.fixture(autouse=True)
    def _set_key(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test-config")

    def test_config_requires_api_key(self, monkeypatch):
        """没有 API key 时应抛出 ValueError。"""
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        with pytest.raises(ValueError, match="LLM_API_KEY"):
            from server.config import Config
            Config()

    def test_config_loads_defaults(self, monkeypatch):
        # load_dotenv 不会覆盖已有环境变量，setenv 后 reload 即可隔离 .env
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com")
        monkeypatch.setenv("INSTANT_MEMORY_SIZE", "200")
        monkeypatch.setenv("EVOLUTION_DEFAULT_ROUNDS", "20")
        monkeypatch.setenv("EVOLUTION_MAX_LOOPS", "30")
        monkeypatch.setenv("CHAT_MAX_TOKENS", "2048")
        monkeypatch.setenv("CHAT_MAX_AGENT_LOOP", "15")
        monkeypatch.setenv("MEMORY_LIMIT", "10")
        monkeypatch.setenv("CARE_COOLDOWN_HOURS", "24")
        monkeypatch.setenv("DECAY_HALF_LIFE_DAYS", "15.0")
        monkeypatch.setenv("NOVEL_CHAPTER_MIN_CHARS", "3000")
        monkeypatch.setenv("NOVEL_CHAPTER_MAX_CHARS", "5000")
        monkeypatch.setenv("NOVEL_CYCLE_MAX", "10")
        monkeypatch.setenv("LLM_RETRY_MAX", "3")
        monkeypatch.setenv("EMBEDDING_DIM", "1024")

        from importlib import reload
        import server.config
        reload(server.config)
        c = server.config.Config()
        assert c.LLM_BASE_URL == "https://api.deepseek.com"
        assert c.EVOLUTION_DEFAULT_ROUNDS == 20
        assert c.EVOLUTION_MAX_LOOPS == 30
        assert c.CHAT_MAX_TOKENS == 2048
        assert c.CHAT_MAX_AGENT_LOOP == 15
        assert c.MEMORY_LIMIT == 10
        assert c.INSTANT_MEMORY_SIZE == 200
        assert c.CARE_COOLDOWN_HOURS == 24
        assert c.DECAY_HALF_LIFE_DAYS == 15.0
        assert c.NOVEL_CHAPTER_MIN_CHARS == 3000
        assert c.NOVEL_CHAPTER_MAX_CHARS == 5000
        assert c.NOVEL_CYCLE_MAX == 10
        assert c.LLM_RETRY_MAX == 3
        assert c.EMBEDDING_DIM == 1024

    def test_config_env_overrides(self, monkeypatch):
        monkeypatch.setenv("EVOLUTION_DEFAULT_ROUNDS", "10")
        monkeypatch.setenv("CHAT_TEMPERATURE", "0.9")
        monkeypatch.setenv("MEMORY_LIMIT", "5")
        from importlib import reload
        import server.config
        reload(server.config)
        c = server.config.Config()
        assert c.EVOLUTION_DEFAULT_ROUNDS == 10
        assert c.CHAT_TEMPERATURE == 0.9
        assert c.MEMORY_LIMIT == 5
