# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""字形混淆测试——obfuscate / deobfuscate 双向转换及降级行为。"""
import json
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def reset_module_cache():
    """每次测试前重置混淆模块的内部缓存。"""
    import server.utils.font_obfuscate as fo
    fo._obfuscation_map = None
    yield
    fo._obfuscation_map = None


class TestObfuscate:
    def test_obfuscate_with_valid_key(self, tmp_path, monkeypatch):
        """使用临时 key 文件验证混淆替换。"""
        key = {"你": "祢", "好": "恏", "世": "丗", "界": "畍"}
        key_file = tmp_path / "obfuscation_key.json"
        key_file.write_text(json.dumps(key, ensure_ascii=False), encoding="utf-8")

        import server.utils.font_obfuscate as fo
        monkeypatch.setattr(fo, "_KEY_PATH", key_file)
        fo._obfuscation_map = None

        result = fo.obfuscate("你好世界")
        assert result == "祢恏丗畍"

    def test_obfuscate_preserves_non_chinese(self, tmp_path, monkeypatch):
        """混淆时保留非映射字符（英文、数字、标点）。"""
        key = {"你": "祢"}
        key_file = tmp_path / "obfuscation_key.json"
        key_file.write_text(json.dumps(key, ensure_ascii=False), encoding="utf-8")

        import server.utils.font_obfuscate as fo
        monkeypatch.setattr(fo, "_KEY_PATH", key_file)
        fo._obfuscation_map = None

        result = fo.obfuscate("Hello，你！123")
        assert result == "Hello，祢！123"

    def test_obfuscate_fallback_on_missing_file(self, tmp_path, monkeypatch):
        """映射文件不存在时返回原文。"""
        import server.utils.font_obfuscate as fo
        monkeypatch.setattr(fo, "_KEY_PATH", tmp_path / "nonexistent.json")
        fo._obfuscation_map = None

        result = fo.obfuscate("你好世界")
        assert result == "你好世界"

    def test_obfuscate_fallback_on_empty_key(self, tmp_path, monkeypatch):
        """映射文件为空 dict 时返回原文。"""
        key_file = tmp_path / "obfuscation_key.json"
        key_file.write_text("{}", encoding="utf-8")

        import server.utils.font_obfuscate as fo
        monkeypatch.setattr(fo, "_KEY_PATH", key_file)
        fo._obfuscation_map = None

        result = fo.obfuscate("你好")
        assert result == "你好"


class TestDeobfuscate:
    def test_deobfuscate_roundtrip(self, tmp_path, monkeypatch):
        """混淆后再还原应得到原文。"""
        key = {"你": "祢", "好": "恏", "世": "丗", "界": "畍"}
        key_file = tmp_path / "obfuscation_key.json"
        key_file.write_text(json.dumps(key, ensure_ascii=False), encoding="utf-8")

        import server.utils.font_obfuscate as fo
        monkeypatch.setattr(fo, "_KEY_PATH", key_file)
        fo._obfuscation_map = None

        original = "你好世界"
        obfuscated = fo.obfuscate(original)
        restored = fo.deobfuscate(obfuscated)
        assert restored == original

    def test_deobfuscate_empty_map(self, tmp_path, monkeypatch):
        """空映射时 deobfuscate 返回原文。"""
        import server.utils.font_obfuscate as fo
        monkeypatch.setattr(fo, "_KEY_PATH", tmp_path / "nonexistent.json")
        fo._obfuscation_map = None

        assert fo.deobfuscate("祢恏") == "祢恏"


class TestCacheBehavior:
    def test_key_file_only_loaded_once(self, tmp_path, monkeypatch):
        """映射表应只加载一次（缓存行为）。"""
        key = {"你": "祢"}
        key_file = tmp_path / "obfuscation_key.json"
        key_file.write_text(json.dumps(key, ensure_ascii=False), encoding="utf-8")

        import server.utils.font_obfuscate as fo
        monkeypatch.setattr(fo, "_KEY_PATH", key_file)
        fo._obfuscation_map = None

        fo.obfuscate("你好")
        # 修改 key 文件内容
        key_file.write_text('{"你": "新"}', encoding="utf-8")
        # 由于缓存，仍使用旧映射
        result = fo.obfuscate("你好")
        assert result == "祢好"  # "你"→"祢"，"好"不在映射中保留原样
