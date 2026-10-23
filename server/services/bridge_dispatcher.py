# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""桥接分发器——yinghui → yinghui-dsh-plug bridge（默认 127.0.0.1:8100）的唯一出站通道。

yinghui 是纯领域服务：全部 agent 编排（演化/对话/小说/补全/提取）由外部
bridge 进程驱动 DeepSeek Harness 完成。本模块只做一件事：把触发请求
POST 到 bridge 对应的 agent 端点。

约定：
- 全异步（httpx.AsyncClient 惰性单例，进程退出经 aclose() 释放）；
- wait=False：fire-and-forget 触发，10s 超时（bridge 受理即返，执行结果
  经 SSE / 任务状态回查）；
- wait=True：同步代理（补全/提取 oneshot），由调用方给定长超时等待 JSON；
- 连接失败/超时 raise BridgeUnavailable，由路由层转 503。
"""
import logging

import httpx

from server.config import config

logger = logging.getLogger(__name__)

# fire-and-forget 触发的受理超时
_FIRE_FORGET_TIMEOUT = 10.0


class BridgeUnavailable(Exception):
    """桥接进程不可达或触发请求超时。"""


_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=config.BRIDGE_URL,
            timeout=httpx.Timeout(_FIRE_FORGET_TIMEOUT),
        )
    return _client


async def dispatch(
    agent: str,
    payload: dict,
    *,
    wait: bool = False,
    timeout: float | None = None,
) -> dict:
    """POST {BRIDGE_URL}/{agent}，返回 bridge 的 JSON 响应。

    Args:
        agent: bridge 侧 agent 端点名，如 "evolutions/start-round"、"chats/start"。
        payload: JSON 请求体。
        wait: True 时同步等待结果（oneshot 代理）；False 为 fire-and-forget 触发。
        timeout: 本次请求超时秒数；缺省 wait=False → 10s，wait=True 时由调用方给定。

    Raises:
        BridgeUnavailable: 连接失败或超时（路由层转 503）。
    """
    if timeout is None:
        timeout = _FIRE_FORGET_TIMEOUT if not wait else 300.0
    client = _get_client()
    try:
        resp = await client.post(f"/{agent.lstrip('/')}", json=payload, timeout=timeout)
    except (httpx.TimeoutException, httpx.TransportError) as e:
        logger.error("桥接不可达 agent=%s url=%s: %s", agent, config.BRIDGE_URL, e)
        raise BridgeUnavailable(
            f"桥接服务未启动或无响应：{config.BRIDGE_URL}（{e.__class__.__name__}）"
        ) from e
    resp.raise_for_status()
    if not resp.content:
        return {}
    return resp.json()


async def aclose():
    """进程退出时释放底层连接池（lifespan shutdown 调用）。"""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("桥接分发器 HTTP 客户端已关闭")
