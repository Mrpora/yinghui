# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""bridge_dispatcher 单元测试——bridge 非 2xx / 非法 JSON 包装为 BridgeUnavailable。

用 httpx.MockTransport 直替换底层 client（不 patch dispatch 本身），
覆盖真实 dispatch 代码路径（raise_for_status / resp.json）。
"""
import asyncio

import httpx
import pytest

from server.services import bridge_dispatcher as bd


def _install_transport(monkeypatch, handler):
    client = httpx.AsyncClient(
        base_url="http://bridge.test",
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(bd, "_client", client)


def test_dispatch_wraps_http_status_error(monkeypatch):
    """bridge 返回非 2xx → BridgeUnavailable（message 附状态码），不裸穿透 500。"""
    _install_transport(monkeypatch, lambda req: httpx.Response(500, text="boom"))
    with pytest.raises(bd.BridgeUnavailable) as ei:
        asyncio.run(bd.dispatch("evolutions/start-round", {}))
    assert "HTTP 500" in str(ei.value)
    assert "evolutions/start-round" in str(ei.value)


def test_dispatch_wraps_invalid_json(monkeypatch):
    """bridge 返回 2xx 但响应体非法 JSON → BridgeUnavailable（message 附状态码）。"""
    _install_transport(monkeypatch, lambda req: httpx.Response(200, content=b"not-json"))
    with pytest.raises(bd.BridgeUnavailable) as ei:
        asyncio.run(bd.dispatch("worlds/complete-config", {}))
    assert "HTTP 200" in str(ei.value)


def test_dispatch_success_passthrough(monkeypatch):
    """正常 2xx JSON 原样返回。"""
    _install_transport(monkeypatch, lambda req: httpx.Response(200, json={"ok": 1}))
    assert asyncio.run(bd.dispatch("chats/start", {})) == {"ok": 1}


def test_dispatch_empty_body_returns_empty_dict(monkeypatch):
    """2xx 空 body → {}（既有语义不变）。"""
    _install_transport(monkeypatch, lambda req: httpx.Response(200))
    assert asyncio.run(bd.dispatch("novels/generate", {})) == {}
