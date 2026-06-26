# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""小说生成工具——write_file / read_file / review_chapter / assemble。"""

import json
import logging
import re
import statistics
from pathlib import Path

logger = logging.getLogger(__name__)


def _resolve_path(work_dir: Path, path: str) -> Path | None:
    """安全解析工作目录内路径，穿越时返回 None。"""
    resolved = (work_dir / path).resolve()
    try:
        resolved.relative_to(work_dir.resolve())
    except ValueError:
        return None
    return resolved


def write_file(work_dir: Path, path: str, content: str) -> dict:
    """写入内容到工作目录内的指定路径。"""
    resolved = _resolve_path(work_dir, path)
    if resolved is None:
        return {"success": False, "error": "路径不在工作目录内"}
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return {"success": True, "path": path}
    except OSError as e:
        return {"success": False, "error": str(e)}


def read_file(work_dir: Path, path: str, search: str | None = None) -> dict:
    """读取工作目录内文件，支持关键词定位。"""
    resolved = _resolve_path(work_dir, path)
    if resolved is None:
        return {"content": "", "matches": 0, "exists": False, "error": "路径不在工作目录内"}
    if not resolved.is_file():
        return {"content": "", "matches": 0, "exists": False}

    try:
        text = resolved.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        return {"content": "", "matches": 0, "exists": True, "error": str(e)}

    if search is None or search == "":
        return {"content": text, "matches": 0, "exists": True}

    lower_text = text.lower()
    lower_search = search.lower()
    matches = []
    start = 0
    while True:
        idx = lower_text.find(lower_search, start)
        if idx == -1:
            break
        ctx_start = max(0, idx - 150)
        ctx_end = min(len(text), idx + len(search) + 150)
        matches.append(text[ctx_start:ctx_end])
        start = idx + len(search)

    return {"content": "\n---\n".join(matches) if matches else "",
            "matches": len(matches), "exists": True}


def _count_chinese_chars(text: str) -> int:
    """统计中文字符数（含中文标点）。"""
    count = 0
    for ch in text:
        if '一' <= ch <= '鿿' or ch in '，。！？；：、""''【】《》（）……——':
            count += 1
    return count


def _make_chars_verdict(wc: int, min_c: int, max_c: int) -> str:
    if wc < min_c:
        return f"字数偏少，不足 {min_c} 字，建议扩写"
    elif wc > max_c:
        return f"字数偏多，超过 {max_c} 字，建议压缩"
    else:
        return f"字数达标，在 {min_c}-{max_c} 范围内"


def _compute_sentence_stats(text: str) -> dict:
    sentences = re.split(r'[。！？；\n]', text)
    lengths = [_count_chinese_chars(s) for s in sentences if s.strip()]
    if not lengths:
        return {"count": 0, "mean": 0, "std": 0, "p10": 0, "p50": 0, "p90": 0,
                "buckets": {"<=5": 0, "6-10": 0, "11-20": 0, "21-35": 0, ">35": 0}}
    lengths.sort()
    n = len(lengths)
    return {
        "count": n,
        "mean": round(sum(lengths) / n, 1),
        "std": round(statistics.stdev(lengths), 1) if n >= 2 else 0,
        "p10": lengths[int(n * 0.1)] if n >= 10 else lengths[0],
        "p50": lengths[n // 2],
        "p90": lengths[int(n * 0.9)] if n >= 10 else lengths[-1],
        "buckets": {
            "<=5": sum(1 for l in lengths if l <= 5),
            "6-10": sum(1 for l in lengths if 6 <= l <= 10),
            "11-20": sum(1 for l in lengths if 11 <= l <= 20),
            "21-35": sum(1 for l in lengths if 21 <= l <= 35),
            ">35": sum(1 for l in lengths if l > 35),
        },
    }


def _count_same_length_groups(text: str) -> int:
    sentences = re.split(r'[。！？；\n]', text)
    lengths = [_count_chinese_chars(s) for s in sentences if s.strip()]
    if len(lengths) < 3:
        return 0
    groups = 0
    for i in range(len(lengths) - 2):
        a, b, c = lengths[i], lengths[i + 1], lengths[i + 2]
        if abs(a - b) < 5 and abs(b - c) < 5 and abs(a - c) < 5:
            groups += 1
    return groups


def _precheck_chapter(text: str) -> dict:
    return {
        "star_count": len(re.findall(r'\n\*{3}\n', text)),
        "dash_count": len(re.findall(r'\n---\n', text)),
        "simile_estimate": len(re.findall(r'像是|仿佛|似乎|如同|宛如', text)),
        "fangfo_count": len(re.findall(r'仿佛', text)),
        "wanru_count": len(re.findall(r'宛如', text)),
        "ai_adverbs": {
            "渐渐": len(re.findall(r'渐渐', text)),
            "缓缓": len(re.findall(r'缓缓', text)),
            "突然": len(re.findall(r'突然', text)),
            "猛地": len(re.findall(r'猛地', text)),
            "轻轻": len(re.findall(r'轻轻', text)),
            "深深": len(re.findall(r'深深', text)),
            "默默": len(re.findall(r'默默', text)),
            "静静": len(re.findall(r'静静', text)),
        },
        "emotion_cliches": {
            "胃里翻涌/攥": len(re.findall(r'胃里.*翻涌|胃里.*攥', text)),
            "倒吸凉气": len(re.findall(r'倒吸.*凉气', text)),
            "心里一紧/心头一颤": len(re.findall(r'心里一紧|心头一颤|心头一震', text)),
        },
        "emotion_tags": {
            "胃里翻涌": len(re.findall(r'胃里翻涌', text)),
            "指尖攥紧": len(re.findall(r'指尖攥紧', text)),
            "心跳漏了一拍": len(re.findall(r'心跳漏了一拍', text)),
            "瞳孔一缩": len(re.findall(r'瞳孔一缩', text)),
        },
        "consecutive_same_length_groups": _count_same_length_groups(text),
        "subtle_ai_templates": {
            "呼吸停顿": len(re.findall(r'呼吸(?:停|停滞|屏住|凝滞)了(?:一瞬|半拍|片刻|一下)', text)),
            "沉默填充": len(re.findall(r'沉默(?:了|着)(?:半晌|许久|片刻|了很久|了一会儿)', text)),
            "静止填充": len(re.findall(r'一动不动地(?:站|蹲|坐|待)了很久', text)),
        },
        "de_count": len(re.findall(r'的', text)),
        "sentence_stats": _compute_sentence_stats(text),
    }


def assemble(work_dir: Path) -> dict:
    """扫描 chapters/ 目录，按序号拼合全书。"""
    chapters_dir = work_dir / "chapters"
    if not chapters_dir.is_dir():
        return {"success": False, "chapter_count": 0, "total_chars": 0,
                "error": "无章节文件"}

    files = list(chapters_dir.glob("ch_*.md"))
    if not files:
        return {"success": False, "chapter_count": 0, "total_chars": 0,
                "error": "无章节文件"}

    def _extract_num(p: Path) -> int:
        m = re.search(r'ch_(\d+)\.md$', p.name)
        return int(m.group(1)) if m else 10 ** 9

    files.sort(key=_extract_num)

    parts = ["***本小说由 AI 基于世界演化记录自动转化而成***\n\n"]
    total_chars = 0
    for idx, f in enumerate(files, start=1):
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            logger.error("组装时读取章节失败 %s: %s", f.name, e)
            continue
        # 先剥离已有"第x章"前缀（LLM 可能不稳定输出），再统一编号
        text = re.sub(r'^#\s*第[一二三四五六七八九十百千0-9]+章\s*', '# ', text)
        text = re.sub(r'^# ', f'# 第{idx}章 ', text, count=1)
        parts.append(text)
        total_chars += _count_chinese_chars(text)

    full_text = "\n\n---\n\n".join(parts) + "\n\n（全篇完）\n"
    output_dir = work_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "novel_full.md"
    output_path.write_text(full_text, encoding="utf-8")
    return {"success": True, "output_path": "output/novel_full.md",
            "chapter_count": len(files), "total_chars": total_chars}


async def review_chapter(
    work_dir: Path,
    chapter_index: int,
    chapter_path: str,
    *,
    llm_client,
    reviewer_system_prompt: str,
    reviewer_model: str,
    reviewer_reasoning_effort: str,
    reviewer_max_tokens: int,
    chapter_min_chars: int,
    chapter_max_chars: int,
) -> dict:
    """调用独立审稿 LLM 审查章节，返回结构化报告。"""
    if not isinstance(chapter_index, int) or chapter_index < 1:
        return {"passed": False, "report": f"章节序号须 >=1，收到: {chapter_index}",
                "word_count": 0, "chars_verdict": "不适用"}

    resolved = _resolve_path(work_dir, chapter_path)
    if resolved is None:
        return {"passed": False, "report": "章节路径不在工作目录内",
                "word_count": 0, "chars_verdict": "不适用"}
    if not resolved.is_file():
        return {"passed": False, "report": f"章节文件 {chapter_path} 不存在",
                "word_count": 0, "chars_verdict": "不适用"}

    try:
        chapter_text = resolved.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        return {"passed": False, "report": f"无法读取: {e}",
                "word_count": 0, "chars_verdict": "不适用"}

    word_count = _count_chinese_chars(chapter_text)
    chars_verdict = _make_chars_verdict(word_count, chapter_min_chars, chapter_max_chars)

    precheck = _precheck_chapter(chapter_text)
    same_len = precheck["consecutive_same_length_groups"]
    emotion_tags_total = sum(precheck["emotion_tags"].values())
    subtle_total = sum(precheck["subtle_ai_templates"].values())

    precheck_summary = (
        f"## 程序预检数据\n\n"
        f"- 分场符 `***`：{precheck['star_count']} 处\n"
        f"- 残留 `---`：{precheck['dash_count']} 处（>0 → BLOCKING）\n"
        f"- 比喻词：{precheck['simile_estimate']}（仿佛 {precheck['fangfo_count']}/2，宛如 {precheck['wanru_count']}/2）\n"
        f"- AI 高频副词：{' '.join(f'{k}({v})' for k, v in precheck['ai_adverbs'].items() if v > 0) or '（无）'}\n"
        f"- 情绪万能句式：{sum(precheck['emotion_cliches'].values())} 处\n"
        f"- 情绪标签词：{emotion_tags_total} 处\n"
        f"- 连续同长句组数（≥3 句差<5 字）：{same_len} 组"
        f"{' → WARNING (≥4)' if same_len >= 4 else ''}\n"
        f"- 隐蔽 AI 模板（WARNING 级）：{subtle_total} 处\n"
        f"- \"的\"字总数：{precheck['de_count']}\n"
        f"- 句子长度分布：count={precheck['sentence_stats']['count']}"
        f" mean={precheck['sentence_stats']['mean']}"
        f" std={precheck['sentence_stats']['std']}"
        f" p50={precheck['sentence_stats']['p50']}\n"
    )

    plan_path = work_dir / "plan.md"
    state_path = work_dir / "state.md"
    plan_text = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else "（尚未创建）"
    state_text = state_path.read_text(encoding="utf-8") if state_path.is_file() else "（尚未创建）"

    # 判断最后一章
    is_last_chapter = False
    if plan_path.is_file():
        chapter_rows = re.findall(r'\|\s*(\d+)\s*\|', plan_text)
        if chapter_rows:
            total_planned = max(int(n) for n in chapter_rows)
            is_last_chapter = chapter_index >= total_planned

    reviewer_messages = [
        {"role": "system", "content": reviewer_system_prompt},
        {"role": "user", "content": (
            f"请审查第 {chapter_index} 章。\n"
            f"是否为最后一章：{'是' if is_last_chapter else '否'}。\n\n"
            f"{precheck_summary}\n"
            f"## 章节正文\n\n{chapter_text}\n\n"
            f"## 全书规划（plan.md）\n\n{plan_text}\n\n"
            f"## 跨章状态（state.md）\n\n{state_text}"
        )},
    ]

    try:
        response = await llm_client.generate(
            messages=reviewer_messages,
            reasoning_effort=reviewer_reasoning_effort,
            model=reviewer_model,
            max_tokens=reviewer_max_tokens,
            caller="NovelAgent-Reviewer",
        )
        report = response.content or ""
    except Exception as e:
        logger.error("审稿 LLM 调用失败: %s", e)
        return {"passed": False, "report": f"（审稿服务不可用: {e}）",
                "word_count": word_count, "chars_verdict": chars_verdict}

    match = re.search(r'\[passed:\s*(true|false)\]', report, re.IGNORECASE)
    passed = match.group(1).lower() == "true" if match else False

    # 硬门禁
    if word_count < chapter_min_chars:
        passed = False
        shortfall = chapter_min_chars - word_count
        report = (
            f"【硬约束-BLOCKING】字数不达标：当前 {word_count} 字，"
            f"最低 {chapter_min_chars} 字，需扩写 {shortfall} 字。\n\n{report}"
        )
    if precheck["dash_count"] > 0:
        passed = False
        report = (
            f"【硬约束-BLOCKING】检测到 {precheck['dash_count']} 处 `---` 残留。"
            f"`---` 是违禁分场符，请替换为 `***`。\n\n{report}"
        )
    if not passed:
        report = re.sub(r'\[passed:\s*true\]', '[passed: false]（被程序硬门禁覆盖）',
                        report, flags=re.IGNORECASE)

    return {"passed": passed, "report": report, "word_count": word_count,
            "chars_verdict": chars_verdict}
