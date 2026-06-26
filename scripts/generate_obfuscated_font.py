# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""生成混淆字体和字符映射表。

原理：
  - 对每个中文字符 original，随机选取一个 garbled 字符
  - 混淆字体中，garbled 码位上的字形 = original 的字形
  - 前端文本中 original 被替换成 garbled
  - 浏览器用混淆字体渲染，garbled 码位显示出 original 的字形
  - 最终：DOM/源码中是乱码，人眼看到的是正确文字
"""
import json
import random
import sqlite3
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.subset import Subsetter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "app.db"
OUTPUT_DIR = PROJECT_ROOT / "frontend" / "public" / "assets" / "fonts"
KEY_PATH = PROJECT_ROOT / "data" / "obfuscation_key.json"

# Source Han Serif SC = Noto Serif SC（同一字体，不同品牌）
BASE_FONT = Path.home() / "Library/Fonts/SourceHanSerifSC-Regular.otf"


def collect_characters() -> set[str]:
    """从所有未删除的小说中提取中文字符集。"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT content FROM novels WHERE content IS NOT NULL AND content != '' AND is_deleted = 0"
    ).fetchall()
    chars: set[str] = set()
    for r in rows:
        for ch in r["content"]:
            cp = ord(ch)
            if (0x4E00 <= cp <= 0x9FFF or
                0x3000 <= cp <= 0x303F or
                0xFF00 <= cp <= 0xFFEF):
                chars.add(ch)
    conn.close()
    return chars


def generate_mapping(chars: set[str]) -> dict[str, str]:
    """生成 original → garbled 的随机双射映射。"""
    char_list = list(chars)
    shuffled = char_list.copy()
    random.shuffle(shuffled)
    for i in range(len(char_list)):
        if char_list[i] == shuffled[i]:
            j = (i + 1) % len(char_list)
            shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
    return {char_list[i]: shuffled[i] for i in range(len(char_list))}


def create_obfuscated_font(mapping: dict[str, str]):
    """生成混淆字体。

    正确顺序：
    1. Subset：保留 original + garbled + ASCII（保证所有需要的字形都在）
    2. 交换 cmap：garbled 码位 → original 字形
    3. 移除 original 码位（此时 original 字形不再被任何码位引用）
    """
    font = TTFont(BASE_FONT)

    # Step 1: 计算需要保留的所有码位
    all_codepoints: set[int] = set()
    # original 字符（保留其字形，后续会被 garbled 码位引用）
    for original in mapping:
        all_codepoints.add(ord(original))
    # garbled 字符（前端显示用的码位）
    for garbled in mapping.values():
        all_codepoints.add(ord(garbled))
    # ASCII
    for cp in range(32, 127):
        all_codepoints.add(cp)
    # 空白字符
    for cp in [0x0A, 0x0D, 0x09]:
        all_codepoints.add(cp)

    # Step 2: Subset —— 先裁剪到需要的码位，保留字形
    subsetter = Subsetter()
    subsetter.populate(unicodes=list(all_codepoints))
    subsetter.subset(font)

    # Step 3: 交换 cmap —— garbled 码位指向 original 字形
    # 必须先读后写：避免 A→X, X→B 这种链式映射导致的就地修改错误
    cmap_table = font["cmap"]
    for table in cmap_table.tables:
        if not hasattr(table, "cmap"):
            continue
        # Pass 1: 读取所有 original 码位对应的字形名
        glyph_snapshot: dict[int, str] = {}
        for original in mapping:
            orig_cp = ord(original)
            if orig_cp in table.cmap:
                glyph_snapshot[orig_cp] = table.cmap[orig_cp]
        # Pass 2: 将 garbled 码位指向 original 字形
        for original, garbled in mapping.items():
            orig_cp = ord(original)
            garbled_cp = ord(garbled)
            if orig_cp in glyph_snapshot and garbled_cp in table.cmap:
                table.cmap[garbled_cp] = glyph_snapshot[orig_cp]

    # Step 4: 计算最终保留的码位（garbled + ASCII，移除 original）
    final_codepoints: set[int] = set()
    for garbled in mapping.values():
        final_codepoints.add(ord(garbled))
    for cp in range(32, 127):
        final_codepoints.add(cp)
    for cp in [0x0A, 0x0D, 0x09]:
        final_codepoints.add(cp)

    # Step 5: 从 cmap 中移除 original 码位
    for table in cmap_table.tables:
        if not hasattr(table, "cmap"):
            continue
        table.cmap = {
            cp: glyph
            for cp, glyph in table.cmap.items()
            if cp in final_codepoints
        }

    # Step 6: 删除可变字体相关表
    for tag in ["fvar", "gvar", "MVAR", "avar", "STAT"]:
        if tag in font:
            del font[tag]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    woff2_path = OUTPUT_DIR / "novel-obfuscated.woff2"
    font.flavor = "woff2"
    font.save(str(woff2_path))
    print(f"  混淆字体已保存: {woff2_path}")

    size_kb = woff2_path.stat().st_size / 1024
    print(f"  字体大小: {size_kb:.0f} KB")
    print(f"  保留码位数: {len(final_codepoints)}")


def main():
    random.seed(42)

    print("1/3 收集字符集...")
    chars = collect_characters()
    print(f"  共 {len(chars)} 个不重复中文字符")

    print("2/3 生成字符映射...")
    mapping = generate_mapping(chars)
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(KEY_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False)
    print(f"  映射已保存: {KEY_PATH}")

    print("3/3 生成混淆字体...")
    create_obfuscated_font(mapping)

    print("\n✅ 完成")


if __name__ == "__main__":
    main()
