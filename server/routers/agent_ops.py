# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""agent_ops 路由——/api/agent/* 全量领域操作接口（MCP server 与桥接进程回写用）。

仅回环使用、无鉴权。逐端点薄壳：meta 级存在性校验与业务逻辑全部在
agent_ops_service（依赖经 Depends 显式注入，服务层无模块级单例）。
SSE 词汇冻结：演化 round_start/timeline_event/branches/session_paused/
round_end/session_ended/relationships；聊天 thinking/retrieving/memorizing/
token/done/error。
"""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from server.dependencies import get_sse_manager
from server.services import agent_ops_service as svc
from server.storage.sqlite_client import get_db

router = APIRouter(prefix="/api/agent", tags=["agent-ops"])


# ── 请求模型 ──

class TimelineEventRequest(BaseModel):
    type: str
    content: str
    character: str | None = None
    motive: str | None = None
    inner_thoughts: str | None = None
    source: str | None = None


class RoundSummaryRequest(BaseModel):
    round: int
    summary: str


class RelationshipEdge(BaseModel):
    from_character: str
    to_character: str
    description: str


class UpdateRelationshipsRequest(BaseModel):
    edges: list[RelationshipEdge]


class BranchItem(BaseModel):
    title: str
    description: str


class PushBranchesRequest(BaseModel):
    branches: list[BranchItem]


class RecoverRequest(BaseModel):
    reason: str


class CharacterContextRequest(BaseModel):
    message: str


class RetrieveMemoriesRequest(BaseModel):
    user_id: str
    novel_id: str
    character_id: str
    query: str
    top_k: int | None = Field(default=None, ge=1)


class WriteMemoryRequest(BaseModel):
    user_id: str
    novel_id: str
    character_id: str
    content: str
    type: str
    importance: float | None = None  # 契约兼容字段（无落库列，忽略）
    expires_at: int | None = None


class UpdateMemoryRequest(BaseModel):
    content: str | None = None
    type: str | None = None
    importance: float | None = None  # 契约兼容字段（无落库列，忽略）
    expires_at: int | None = None


class ExtremeEmotionRequest(BaseModel):
    user_id: str
    novel_id: str
    character_id: str
    summary: str
    level: float


class ChatMessageAppendRequest(BaseModel):
    message: dict


class ChatStageRequest(BaseModel):
    stage: Literal["thinking", "retrieving", "memorizing"]


class ChatDoneRequest(BaseModel):
    character_message: dict


class SaveChapterRequest(BaseModel):
    index: int = Field(ge=1)
    title: str = ""
    content: str


class PrecheckRequest(BaseModel):
    index: int = Field(ge=1)


class TaskFailRequest(BaseModel):
    reason: str


class CareEchoRequest(BaseModel):
    user_id: str
    novel_id: str
    character_id: str
    is_active: bool = True


# ═══════════════════════════════════════════════════════════
# 演化组
# ═══════════════════════════════════════════════════════════

@router.get("/evolutions/{evolution_id}/world-config")
async def get_world_config(evolution_id: str, db=Depends(get_db)):
    """读世界配置 + 角色列表（软删世界不拦截）。"""
    return await svc.get_world_config(db, evolution_id)


@router.get("/evolutions/{evolution_id}/timeline")
async def get_timeline(
    evolution_id: str,
    since_round: int = Query(0, ge=0),
    db=Depends(get_db),
):
    """读时间线/关系/轮次进度。"""
    return await svc.get_timeline(db, evolution_id, since_round)


@router.post("/evolutions/{evolution_id}/timeline-event")
async def write_timeline_event(
    evolution_id: str, req: TimelineEventRequest,
    db=Depends(get_db), sse=Depends(get_sse_manager),
):
    """写时间线事件（类型校验）+ SSE timeline_event。"""
    event = await svc.write_timeline_event(
        db, sse, evolution_id,
        event_type=req.type, content=req.content, character=req.character,
        motive=req.motive, inner_thoughts=req.inner_thoughts, source=req.source,
    )
    return {"event": event}


@router.post("/evolutions/{evolution_id}/round-summary")
async def write_round_summary(
    evolution_id: str, req: RoundSummaryRequest,
    db=Depends(get_db), sse=Depends(get_sse_manager),
):
    """写轮总结（内部写 round_summary 时间线事件，走同一 SSE）。"""
    event = await svc.write_round_summary(
        db, sse, evolution_id, req.round, req.summary)
    return {"event": event}


@router.post("/evolutions/{evolution_id}/relationships")
async def update_relationships(
    evolution_id: str, req: UpdateRelationshipsRequest,
    db=Depends(get_db), sse=Depends(get_sse_manager),
):
    """合并关系边 + SSE relationships。"""
    return await svc.update_relationships(
        db, sse, evolution_id, [edge.model_dump() for edge in req.edges])


@router.get("/evolutions/{evolution_id}/branches/pending")
async def get_pending_branches(evolution_id: str, db=Depends(get_db)):
    """读待决分支（timeline 最后一条 branch_options 解析，容错同前端）。"""
    return {"branches": await svc.get_pending_branches(db, evolution_id)}


@router.post("/evolutions/{evolution_id}/branches")
async def push_branches(
    evolution_id: str, req: PushBranchesRequest,
    db=Depends(get_db), sse=Depends(get_sse_manager),
):
    """推分支 + SSE [branches, session_paused(conflict)] + 置 PAUSED（仅 RUNNING）。"""
    return await svc.push_branches(
        db, sse, evolution_id, [b.model_dump() for b in req.branches])


@router.post("/evolutions/{evolution_id}/complete-round")
async def complete_round(
    evolution_id: str, db=Depends(get_db), sse=Depends(get_sse_manager),
):
    """收束回合：额度用尽 → ENDED + session_ended；否则 WAITING_NEXT_ROUND + round_end。"""
    return await svc.complete_round(db, sse, evolution_id)


@router.post("/evolutions/{evolution_id}/recover")
async def recover_session(
    evolution_id: str, req: RecoverRequest,
    db=Depends(get_db), sse=Depends(get_sse_manager),
):
    """回收函数：RUNNING → WAITING_NEXT_ROUND + SSE [error, round_end]；幂等。"""
    return await svc.recover_session(db, sse, evolution_id, req.reason)


@router.get("/evolutions/{evolution_id}/characters/{name}/context")
async def get_character_context(evolution_id: str, name: str, db=Depends(get_db)):
    """读角色持久化上下文镜像。"""
    return {"messages": await svc.get_character_context(db, evolution_id, name)}


@router.post("/evolutions/{evolution_id}/characters/{name}/context")
async def append_character_context(
    evolution_id: str, name: str, req: CharacterContextRequest,
    db=Depends(get_db),
):
    """追加角色上下文（system 消息）并持久化。"""
    messages = await svc.append_character_context(db, evolution_id, name, req.message)
    return {"messages": messages}


@router.get("/evolutions/{evolution_id}/characters/{name}/profile")
async def get_character_profile(evolution_id: str, name: str, db=Depends(get_db)):
    """读角色人设（world_characters 行全字段）。"""
    return {"character": await svc.get_character_profile(db, evolution_id, name)}


# ═══════════════════════════════════════════════════════════
# 聊天组
# ═══════════════════════════════════════════════════════════

@router.post("/memories/retrieve")
async def retrieve_memories(req: RetrieveMemoriesRequest, db=Depends(get_db)):
    """记忆混合检索（retrieval_service 直通）。"""
    memories = await svc.retrieve_memories(
        db, req.user_id, req.novel_id, req.character_id, req.query, req.top_k)
    return {"memories": memories}


@router.get("/memories/user-facts")
async def list_user_facts(
    user_id: str = Query(...), novel_id: str = Query(...),
    db=Depends(get_db),
):
    """全量 user_fact 记忆读取（chat_flow 直注入用）。"""
    return {"memories": await svc.list_user_facts(db, user_id, novel_id)}


@router.post("/memories")
async def write_memory(req: WriteMemoryRequest, db=Depends(get_db)):
    """写永久记忆（容量满 → 409）。"""
    return await svc.write_memory(
        db, req.user_id, req.novel_id, req.character_id,
        req.content, req.type, req.expires_at)


@router.patch("/memories/{memory_id}")
async def update_memory(memory_id: str, req: UpdateMemoryRequest, db=Depends(get_db)):
    """更新记忆（内容/类型/过期时间）。"""
    return await svc.update_memory(
        db, memory_id, req.content, req.type, req.expires_at)


@router.delete("/memories/{memory_id}")
async def delete_memory(memory_id: str, db=Depends(get_db)):
    """删除记忆。"""
    return await svc.delete_memory(db, memory_id)


@router.post("/safety/extreme-emotion")
async def report_extreme_emotion(req: ExtremeEmotionRequest, db=Depends(get_db)):
    """极端情绪安全上报（写 logs/safety.log）。"""
    return await svc.report_extreme_emotion(
        db, req.user_id, req.novel_id, req.character_id, req.summary, req.level)


@router.get("/chats/{chat_id}/history")
async def get_chat_history(
    chat_id: str, last_n: int = Query(20, ge=1), db=Depends(get_db),
):
    """读对话历史最近 last_n 条。"""
    return {"messages": await svc.get_chat_history(db, chat_id, last_n)}


@router.get("/novel-characters/{character_id}/snapshot")
async def get_character_snapshot(character_id: str, db=Depends(get_db)):
    """读角色快照（novel_characters 行）。"""
    return {"snapshot": await svc.get_character_snapshot(db, character_id)}


@router.post("/chats/{chat_id}/messages")
async def append_chat_message(
    chat_id: str, req: ChatMessageAppendRequest, db=Depends(get_db),
):
    """追加对话消息并持久化（bridge 写角色消息用）。"""
    return await svc.append_chat_message(db, chat_id, req.message)


@router.post("/chats/{chat_id}/stage")
async def emit_chat_stage(
    chat_id: str, req: ChatStageRequest,
    db=Depends(get_db), sse=Depends(get_sse_manager),
):
    """发聊天阶段事件（SSE thinking/retrieving/memorizing）。"""
    await svc.emit_chat_stage(db, sse, chat_id, req.stage)
    return {"ok": True}


@router.post("/chats/{chat_id}/done")
async def chat_done(
    chat_id: str, req: ChatDoneRequest,
    db=Depends(get_db), sse=Depends(get_sse_manager),
):
    """持久化角色消息 + 假流式 token* + done（复刻原 chat_agent 行为）。"""
    return await svc.chat_done(db, sse, chat_id, req.character_message)


# ═══════════════════════════════════════════════════════════
# 小说组
# ═══════════════════════════════════════════════════════════

@router.post("/novel-tasks/{task_id}/chapters")
async def save_chapter(task_id: str, req: SaveChapterRequest, db=Depends(get_db)):
    """写章节文件 chapters/ch_{index}.md。"""
    return await svc.save_chapter(db, task_id, req.index, req.title, req.content)


@router.get("/novel-tasks/{task_id}/chapters/{index}")
async def read_chapter(task_id: str, index: int, db=Depends(get_db)):
    """读章节文件内容。"""
    return {"content": await svc.read_chapter(db, task_id, index)}


@router.post("/novel-tasks/{task_id}/precheck")
async def precheck_chapter(task_id: str, req: PrecheckRequest, db=Depends(get_db)):
    """确定性硬门检查（字数 + `---` 残留；AI 腔/句长统计随响应返回）。"""
    return await svc.precheck_task_chapter(db, task_id, req.index)


@router.post("/novel-tasks/{task_id}/assemble")
async def assemble_novel(
    task_id: str, db=Depends(get_db), sse=Depends(get_sse_manager),
):
    """拼卷落库完结（novels 行写全文+快照、任务 completed、SSE completed）。"""
    return await svc.assemble_novel(db, sse, task_id)


@router.get("/novel-tasks/{task_id}")
async def get_task(task_id: str, db=Depends(get_db)):
    """读任务全字段。"""
    return await svc.get_task(db, task_id)


@router.post("/novel-tasks/{task_id}/fail")
async def fail_task(
    task_id: str, req: TaskFailRequest,
    db=Depends(get_db), sse=Depends(get_sse_manager),
):
    """任务置 failed + SSE error。"""
    return await svc.fail_task(db, sse, task_id, req.reason)


@router.get("/novels/{novel_id}/source")
async def get_novel_source(novel_id: str, db=Depends(get_db)):
    """读演化记录 + world 快照 + 角色（写作/提取种子）。"""
    return await svc.get_novel_source(db, novel_id)


@router.get("/novels/{novel_id}/text")
async def get_novel_text(novel_id: str, db=Depends(get_db)):
    """读已生成全文（提取器输入）。"""
    return await svc.get_novel_text(db, novel_id)


# ═══════════════════════════════════════════════════════════
# 通用
# ═══════════════════════════════════════════════════════════

@router.post("/care/echo")
async def care_echo(req: CareEchoRequest, db=Depends(get_db)):
    """关怀回响判定（care_service.judge_and_prepare_care 直通）。"""
    return await svc.care_echo(
        db, req.user_id, req.novel_id, req.character_id, req.is_active)
