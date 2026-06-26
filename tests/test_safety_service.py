# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""安全报警服务测试——send_alert 日志写入与文件管理。"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock


class TestSendAlert:
    def test_send_alert_returns_success(self, monkeypatch):
        """send_alert 应返回成功状态。"""
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        from server.services.safety_service import send_alert
        result = send_alert("测试用户", "我很难过", "极端情绪检测")
        assert result == {"status": "success"}

    def test_send_alert_writes_to_log_file(self, tmp_path, monkeypatch):
        """send_alert 应写入安全日志文件。"""
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        import server.services.safety_service as ss
        monkeypatch.setattr(ss, "LOG_DIR", tmp_path)

        # 重置全局 alert logger 以使用新路径
        ss._alert_logger = None

        ss.send_alert("用户A", "测试原文", "测试原因")

        log_files = list(tmp_path.glob("safety.log*"))
        assert len(log_files) > 0
        content = log_files[0].read_text(encoding="utf-8")
        assert "用户A" in content
        assert "测试原文" in content
        assert "测试原因" in content
        assert "萦回安全报警" in content

    def test_send_alert_logger_cached(self, monkeypatch):
        """第二次调用应复用已缓存的 logger。"""
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        import server.services.safety_service as ss
        ss._alert_logger = None

        result1 = ss.send_alert("U1", "msg1", "reason1")
        logger1 = ss._alert_logger
        result2 = ss.send_alert("U2", "msg2", "reason2")
        logger2 = ss._alert_logger

        assert result1 == result2 == {"status": "success"}
        assert logger1 is logger2
