# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""演化路由——会话生命周期 + 轮次推进 + 分支选择 + 剧情干预 + SSE 事件流。

LLM 编排已外移至 yinghui-dsh-plug bridge：start-round / select-branch /
custom-event / intervene 为 fire-and-forget 触发（dispatcher POST 不可达 → 503）。
状态迁移所有权在本路由层（spec §4.1）：start-round 在 dispatch 成功后原子地
自增轮次 + 置 RUNNING + SSE round_start；select-branch / custom-event 在
dispatch 成功后写 user_decision + 置 RUNNING（失败保持 PAUSED 可重试）。
"""
import asyncio
import json
import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse

from server.models.schemas import (
    CreateSessionRequest, StartRoundResponse,
    SelectBranchRequest, SelectBranchResponse,
    CustomEventRequest, CustomEventResponse,
    TimelineResponse,
)
from server.models.session import SessionStatus
from server.dependencies import (
    get_session_manager, get_sse_manager,
)
from server.routers._dispatch import dispatch_or_503
from server.services import agent_ops_service as agent_svc
from server.storage.sqlite_client import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/evolutions", tags=["evolutions"])


# ── 会话列表 ──

@router.get("/list")
async def list_evolutions(
    user_id: str = Query(...),
    mgr=Depends(get_session_manager),
):
    sessions = await mgr.list_user_sessions(user_id)
    return {"sessions": sessions}


# ── 创建会话 ──

@router.post("/create", status_code=201)
async def create_evolution(
    req: CreateSessionRequest,
    mgr=Depends(get_session_manager),
):
    session = await mgr.create(req.user_id, req.world_id)
    return {
        "evolution_id": session.id,
        "user_id": session.user_id,
        "world_id": session.world_id,
        "status": session.status.value,
        "max_rounds": session.max_rounds,
        "created_at": session.created_at,
        "world_config": asdict(session.world_config) if session.world_config else None,
    }


# ── 会话详情 ──

@router.get("/detail")
async def get_evolution_detail(
    evolution_id: str = Query(...),
    user_id: str = Query(...),
    mgr=Depends(get_session_manager),
):
    s = await mgr.get(evolution_id, user_id)
    return {
        "evolution_id": s.id,
        "user_id": s.user_id,
        "world_id": s.world_id,
        "status": s.status.value,
        "current_round": s.current_round,
        "max_rounds": s.max_rounds,
        "created_at": s.created_at,
        "character_names": s.character_names,
        "world_config": asdict(s.world_config) if s.world_config else None,
    }


# ── 删除会话 ──

@router.post("/delete")
async def delete_evolution(
    evolution_id: str = Query(...),
    user_id: str = Query(...),
    mgr=Depends(get_session_manager),
):
    await mgr.delete(evolution_id, user_id)
    return {"status": "deleted", "evolution_id": evolution_id}


# ── 启动轮次 ──

@router.post("/start-round", response_model=StartRoundResponse)
async def start_round(
    evolution_id: str = Query(...),
    user_id: str = Query(...),
    mgr=Depends(get_session_manager),
    sse=Depends(get_sse_manager),
):
    s = await mgr.get(evolution_id, user_id)
    if s.status not in (SessionStatus.IDLE, SessionStatus.WAITING_NEXT_ROUND):
        raise HTTPException(409, "当前状态不允许启动新轮次")
    if s.current_round >= s.max_rounds:
        raise HTTPException(400, "演化额度已用完")

    next_round = s.current_round + 1

    # 触发桥接（不可达 → 503，不做任何状态迁移，可直接重试）
    await dispatch_or_503("evolutions/start-round", {
        "evolution_id": evolution_id,
        "user_id": user_id,
        "round": next_round,
    })

    # 原子迁移（唯一所有者）：轮次自增 + 置 RUNNING + SSE round_start
    await mgr.update_meta(
        evolution_id,
        current_round=next_round,
        status=SessionStatus.RUNNING.value,
    )
    await sse.broadcast(f"evolution:{evolution_id}", {
        "type": "round_start",
        "data": {"round": next_round, "max_rounds": s.max_rounds},
    })
    logger.info("启动轮次 evolution_id=%s round=%d", evolution_id, next_round)
    return StartRoundResponse(round=next_round, status="running")


# ── 选择分支 ──

@router.post("/select-branch", response_model=SelectBranchResponse)
async def select_branch(
    evolution_id: str = Query(...),
    user_id: str = Query(...),
    branch_index: int = Query(..., ge=0, le=5),
    mgr=Depends(get_session_manager),
    sse=Depends(get_sse_manager),
    db=Depends(get_db),
):
    s = await mgr.get(evolution_id, user_id)
    if s.status != SessionStatus.PAUSED:
        raise HTTPException(409, "当前状态不允许选择分支")

    # 分支文本从 timeline 的 branch_options 事件解析（与响应体/桥接 prompt 共用）
    branches = await agent_svc.get_pending_branches(db, evolution_id)
    if not branches or branch_index >= len(branches):
        raise HTTPException(400, "分支索引无效")
    branch = branches[branch_index]

    # 触发桥接（不可达 → 503，保持 PAUSED 可重试）
    await dispatch_or_503("evolutions/select-branch", {
        "evolution_id": evolution_id,
        "user_id": user_id,
        "branch_index": branch_index,
    })

    # dispatch 成功后原子段：写 user_decision 时间线事件 + 置 RUNNING
    decision_event = {
        "type": "user_decision",
        "content": f"用户选择了第 {branch_index} 条分支「{branch.get('title', '')}」：{branch.get('description', '')}",
        "round": s.current_round,
        "branch_index": branch_index,
    }
    await mgr.append_timeline_event(evolution_id, decision_event)
    await mgr.update_meta(evolution_id, status=SessionStatus.RUNNING.value)
    await sse.broadcast(f"evolution:{evolution_id}", {
        "type": "timeline_event",
        "data": {"event": decision_event},
    })

    logger.info("选择分支 evolution_id=%s index=%d", evolution_id, branch_index)
    return SelectBranchResponse(
        accepted=True,
        selected_branch={"index": branch_index, "title": branch.get("title", "")},
    )


# ── 自定义事件 ──

@router.post("/custom-event", response_model=CustomEventResponse)
async def custom_event(
    evolution_id: str = Query(...),
    user_id: str = Query(...),
    event_text: str = Query(..., min_length=1, max_length=500),
    mgr=Depends(get_session_manager),
    sse=Depends(get_sse_manager),
):
    s = await mgr.get(evolution_id, user_id)
    if s.status != SessionStatus.PAUSED:
        raise HTTPException(409, "当前状态不允许输入自定义事件")

    # 触发桥接（不可达 → 503，保持 PAUSED 可重试）
    await dispatch_or_503("evolutions/custom-event", {
        "evolution_id": evolution_id,
        "user_id": user_id,
        "event_text": event_text,
    })

    # dispatch 成功后原子段：写 user_decision 时间线事件（文本原样入参）+ 置 RUNNING
    decision_event = {
        "type": "user_decision",
        "content": event_text,
        "round": s.current_round,
    }
    await mgr.append_timeline_event(evolution_id, decision_event)
    await mgr.update_meta(evolution_id, status=SessionStatus.RUNNING.value)
    await sse.broadcast(f"evolution:{evolution_id}", {
        "type": "timeline_event",
        "data": {"event": decision_event},
    })

    logger.info("自定义事件 evolution_id=%s len=%d", evolution_id, len(event_text))
    return CustomEventResponse(accepted=True)


# ── 轮次干预 ──

@router.post("/intervene", response_model=CustomEventResponse)
async def round_intervene(
    evolution_id: str = Query(...),
    user_id: str = Query(...),
    event_text: str = Query(..., min_length=1, max_length=500),
    mgr=Depends(get_session_manager),
    sse=Depends(get_sse_manager),
):
    s = await mgr.get(evolution_id, user_id)
    if s.status != SessionStatus.WAITING_NEXT_ROUND:
        raise HTTPException(409, "当前状态不允许干预剧情，请等待轮次结束后操作")

    summary = f"自定义事件：{event_text}"
    event_dict = {
        "type": "user_intervene", "content": summary, "round": s.current_round,
    }
    await mgr.append_timeline_event(evolution_id, event_dict)
    await sse.broadcast(f"evolution:{evolution_id}", {
        "type": "timeline_event",
        "data": {"event": event_dict},
    })

    # 干预已落库——桥接缺席时仅记录待注入失败，不阻断响应（下次启动由 bridge 扫场）
    try:
        from server.services import bridge_dispatcher
        await bridge_dispatcher.dispatch("evolutions/intervene", {
            "evolution_id": evolution_id,
            "user_id": user_id,
            "event_text": event_text,
            "round": s.current_round,
        })
    except Exception as e:
        logger.warning("干预事件已落库但桥接触发失败 evolution_id=%s: %s",
                       evolution_id, e)

    return CustomEventResponse(accepted=True)


# ── 时间线 ──

@router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(
    evolution_id: str = Query(...),
    user_id: str = Query(...),
    mgr=Depends(get_session_manager),
):
    s = await mgr.get(evolution_id, user_id)
    events, relationships_raw = await asyncio.gather(
        mgr.get_timeline(evolution_id),
        mgr.get_relationships(evolution_id),
    )
    edges = [
        {"from": f, "to": t, "relationship": r}
        for f, targets in relationships_raw.items()
        for t, r in targets.items()
    ]
    return TimelineResponse(
        evolution_id=s.id,
        current_round=s.current_round,
        events=events,
        relationships=edges,
    )


# ── SSE 事件流 ──

@router.get("/events")
async def stream_events(
    evolution_id: str = Query(...),
    user_id: str = Query(...),
    mgr=Depends(get_session_manager),
    sse=Depends(get_sse_manager),
):
    await mgr.get(evolution_id, user_id)
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    channel = f"evolution:{evolution_id}"
    sse.subscribe(channel, queue)

    logger.info("SSE 演化事件连接建立 evolution_id=%s", evolution_id)

    async def generator():
        # 立即发送初始确认，告知客户端 SSE 连接已就绪
        yield "event: connected\ndata: {}\n\n"
        try:
            while True:
                event = await queue.get()
                payload = {"type": event["type"], **event.get("data", {})}
                data = json.dumps(payload, ensure_ascii=False)
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            logger.info("SSE 演化事件断开 evolution_id=%s", evolution_id)
        finally:
            sse.unsubscribe(channel, queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
