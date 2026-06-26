# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""演化路由——会话生命周期 + 轮次推进 + 分支选择 + 剧情干预 + SSE 事件流。"""
import asyncio
import json
import logging
from dataclasses import asdict

from fastapi import APIRouter, BackgroundTasks, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse

from server.models.schemas import (
    CreateSessionRequest, StartRoundRequest, StartRoundResponse,
    SelectBranchRequest, SelectBranchResponse,
    CustomEventRequest, CustomEventResponse,
    TimelineResponse,
)
from server.models.session import SessionStatus
from server.dependencies import (
    get_session_manager, get_evolution_agent, get_sse_manager,
)

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
        "character_names": list(s.character_contexts.keys()) if s.character_contexts else [],
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
    background_tasks: BackgroundTasks = BackgroundTasks(),
    mgr=Depends(get_session_manager),
    pipeline=Depends(get_evolution_agent),
):
    s = await mgr.get(evolution_id, user_id)
    if s.status not in (SessionStatus.IDLE, SessionStatus.WAITING_NEXT_ROUND):
        raise HTTPException(409, "当前状态不允许启动新轮次")
    if s.current_round >= s.max_rounds:
        raise HTTPException(400, "演化额度已用完")

    next_round = s.current_round + 1
    logger.info("启动轮次 evolution_id=%s round=%d", evolution_id, next_round)
    background_tasks.add_task(pipeline.run_round, evolution_id)
    return StartRoundResponse(round=next_round, status="running")


# ── 选择分支 ──

@router.post("/select-branch", response_model=SelectBranchResponse)
async def select_branch(
    evolution_id: str = Query(...),
    user_id: str = Query(...),
    branch_index: int = Query(..., ge=0, le=5),
    mgr=Depends(get_session_manager),
):
    from server.ai.evolution_agent.agent import get_session_branches, resolve_session_event

    s = await mgr.get(evolution_id, user_id)
    if s.status != SessionStatus.PAUSED:
        raise HTTPException(409, "当前状态不允许选择分支")

    branches = get_session_branches(evolution_id)
    if not branches or branch_index >= len(branches):
        raise HTTPException(400, "分支索引无效")
    branch = branches[branch_index]
    logger.info("选择分支 evolution_id=%s index=%d", evolution_id, branch_index)
    success = resolve_session_event(evolution_id, "branch", {"branch_index": branch_index})
    if not success:
        raise HTTPException(409, "会话未处于等待决策状态")
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
):
    from server.ai.evolution_agent_v2.orchestrator import resolve_session_event

    s = await mgr.get(evolution_id, user_id)
    if s.status != SessionStatus.PAUSED:
        raise HTTPException(409, "当前状态不允许输入自定义事件")

    logger.info("自定义事件 evolution_id=%s len=%d", evolution_id, len(event_text))
    success = resolve_session_event(evolution_id, "custom", {"event_text": event_text})
    if not success:
        raise HTTPException(409, "会话未处于等待决策状态")
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

    director_ctx = await mgr.get_context(evolution_id, "director")
    director_ctx.append({
        "role": "user",
        "content": f"[系统通知] 用户在本轮结束后的干预：{summary}。"
                   f"请在下一轮感知派发中将该事件分发给相关角色，自然融入叙事。",
    })
    await mgr.set_context(evolution_id, "director", director_ctx)

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
