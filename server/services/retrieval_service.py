# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
检索服务——双路混合检索（向量 + BM25）+ RRF 融合 + 时间衰减。

路径 1: 向量检索
   - 使用 encode_single 将查询编码为 1024 维归一化向量
   - 在 vec0 虚拟表 (memory_embeddings) 中按余弦距离检索
   - 将距离转为相似度分数 (1.0 - distance)
   - 异常时静默降级，不影响 BM25 路径

路径 2: BM25 文本检索
   - 使用 jieba 分词，在 memory_bm25 表中按词频和检索

RRF 融合:
   - 对两条路径的结果分别按 rank 计算 RRF 分数 (k=60)
   - 同一 memory_id 的 RRF 分数在两路径间求和

时间衰减:
   - 获取所有候选记忆详情（含 character_name）
   - 计算 updated_at 距今天数
   - 应用指数衰减: score * exp(-lambda * days_ago)
   - lambda = ln(2) / DECAY_HALF_LIFE_DAYS
"""

import math
import struct
import logging
from collections import defaultdict


from server.config import config
from server.storage.sqlite_client import get_db, now_ms
from server.services.embedding_service import encode_single
from server.services.memory_service import _tokenize

logger = logging.getLogger(__name__)


async def retrieve(
    query: str,
    user_id: str,
    novel_id: str,
    character_id: str,
    top_k: int = config.RETRIEVAL_TOP_K,
) -> list[dict]:
    """双路混合检索：向量语义匹配 + BM25 关键词匹配，RRF 融合后经时间衰减排序。

    Args:
        query: 检索查询文本
        user_id: 用户 ID
        novel_id: 小说 ID
        character_id: 角色 ID（引用 novel_characters.character_id）
        top_k: 返回结果数量上限

    Returns:
        list[dict]: 每条记忆包含以下字段：
            - memory_id: 记忆唯一标识
            - type: 记忆类型 ("user_fact" 或 "event")
            - content: 记忆文本内容
            - character_name: 角色名称
            - created_at: 创建时间 (ISO 格式)
            - updated_at: 最后更新时间 (ISO 格式)
    """
    db = await get_db()
    now = now_ms()

    # ================================================================
    # 路径 1: 向量检索
    # ================================================================
    vector_results: dict = {}  # memory_id -> {"distance": ..., "similarity": ...}
    try:
        embedding = encode_single(query)
        blob = struct.pack(f"{len(embedding)}f", *embedding)
        cursor = await db.execute(
            """SELECT me.memory_id,
                      vec_distance_cosine(me.vector, ?) AS distance
               FROM memory_embeddings me
               JOIN memories m ON me.memory_id = m.memory_id
               WHERE m.user_id = ?
                 AND m.novel_id = ?
                 AND (m.expires_at IS NULL OR m.expires_at >= ?)
               ORDER BY distance ASC
               LIMIT ?""",
            (blob, user_id, novel_id, now, top_k),
        )
        rows = await cursor.fetchall()
        vector_results = {
            r["memory_id"]: {
                "distance": r["distance"],
                "similarity": 1.0 - r["distance"],
            }
            for r in rows
        }
    except Exception as e:
        # sqlite-vec 未加载等异常 → 静默降级，不影响 BM25 路径
        logger.warning("向量检索失败，降级为纯 BM25: %s", e)

    # ================================================================
    # 路径 2: BM25 文本检索
    # ================================================================
    bm25_results: dict = {}  # memory_id -> score
    tokens = _tokenize(query)
    if tokens:
        placeholders = ",".join("?" * len(tokens))
        cursor = await db.execute(
            f"""SELECT b.memory_id, SUM(b.term_frequency) AS score
                FROM memory_bm25 b
                JOIN memories m ON b.memory_id = m.memory_id
                WHERE b.token IN ({placeholders})
                  AND m.user_id = ?
                  AND m.novel_id = ?
                  AND (m.expires_at IS NULL OR m.expires_at >= ?)
                GROUP BY b.memory_id
                ORDER BY score DESC
                LIMIT ?""",
            (*tokens, user_id, novel_id, now, top_k),
        )
        rows = await cursor.fetchall()
        bm25_results = {r["memory_id"]: r["score"] for r in rows}

    # ================================================================
    # RRF 融合 (Reciprocal Rank Fusion)
    # ================================================================
    # 向量路径：按 similarity 降序（最高相似度 → rank 0）
    vector_ranked = sorted(
        vector_results.items(), key=lambda x: x[1]["similarity"], reverse=True
    )
    # BM25 路径：按 score 降序（最高词频和 → rank 0）
    bm25_ranked = sorted(
        bm25_results.items(), key=lambda x: x[1], reverse=True
    )

    rrf_scores: defaultdict = defaultdict(float)
    for rank, (mem_id, _) in enumerate(vector_ranked):
        rrf_scores[mem_id] += 1.0 / (60 + rank + 1)
    for rank, (mem_id, _) in enumerate(bm25_ranked):
        rrf_scores[mem_id] += 1.0 / (60 + rank + 1)

    if not rrf_scores:
        return []

    # ================================================================
    # 时间衰减
    # ================================================================
    # 获取所有候选记忆的详细信息（含 character_name）
    candidate_ids = list(rrf_scores.keys())
    placeholders = ",".join("?" * len(candidate_ids))
    cursor = await db.execute(
        f"""SELECT m.memory_id, m.memory_type, m.content,
                   json_extract(nc.character_snapshot, '$.name') AS character_name,
                   m.created_at, m.updated_at
            FROM memories m
            JOIN novel_characters nc ON m.character_id = nc.character_id
            WHERE m.memory_id IN ({placeholders})""",
        candidate_ids,
    )
    rows = await cursor.fetchall()

    lambda_decay = math.log(2) / config.DECAY_HALF_LIFE_DAYS
    scored: list = []
    for r in rows:
        updated_at_ms = r["updated_at"]
        days_ago = (now - updated_at_ms) / 86400000.0
        decay_factor = math.exp(-lambda_decay * days_ago)
        final_score = rrf_scores[r["memory_id"]] * decay_factor
        scored.append((final_score, r))

    # 按衰减后得分降序，取 top_k
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    # ================================================================
    # 组装结果
    # ================================================================
    results: list = []
    for _, r in top:
        results.append({
            "memory_id": r["memory_id"],
            "type": r["memory_type"],
            "content": r["content"],
            "character_name": r["character_name"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        })

    return results
