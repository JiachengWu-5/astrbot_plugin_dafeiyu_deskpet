# -*- coding: utf-8 -*-
"""Unit-smoke: WsHub hello exchange."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.protocol import (
    MSG_BRAIN_HELLO,
    MSG_SHELL_HELLO,
    decode,
    encode,
    make_msg,
)
from core.ws_hub import WsHub


def test_hello_exchange():
    asyncio.run(_hello_exchange())


async def _hello_exchange():
    hub = WsHub(host="127.0.0.1", port=18766, kick_old=True)
    received: list[dict] = []

    async def handler(msg: dict) -> None:
        received.append(msg)

    hub.set_handler(handler)
    await hub.start()
    try:
        assert hub.connected is False
        import websockets

        uri = "ws://127.0.0.1:18766"
        async with websockets.connect(uri) as ws:
            await ws.send(encode(make_msg(MSG_SHELL_HELLO, role="shell", version=1)))
            raw = await asyncio.wait_for(ws.recv(), timeout=3)
            reply = decode(raw)
            assert reply["type"] == MSG_BRAIN_HELLO
            assert reply.get("ok") is True
            await asyncio.sleep(0.05)
            assert hub.connected is True
            assert any(m.get("type") == MSG_SHELL_HELLO for m in received)
            await hub.broadcast(make_msg(MSG_BRAIN_HELLO, ok=True, ping=1))
            raw2 = await asyncio.wait_for(ws.recv(), timeout=3)
            assert decode(raw2)["ping"] == 1
    finally:
        await hub.stop()
        assert hub.connected is False
