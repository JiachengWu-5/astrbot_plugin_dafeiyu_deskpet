# -*- coding: utf-8 -*-
"""Unit tests for ScreenLoop scheduler."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.protocol import MSG_REQUEST_SCREENSHOT
from core.screen_loop import ScreenLoop


class FakeHub:
    def __init__(self, connected: bool = False) -> None:
        self._connected = connected
        self.sent: list[dict[str, Any]] = []

    @property
    def connected(self) -> bool:
        return self._connected

    async def broadcast(self, msg: dict[str, Any]) -> None:
        self.sent.append(msg)


def test_tick_broadcasts_when_connected():
    asyncio.run(_tick_broadcasts_when_connected())


async def _tick_broadcasts_when_connected():
    hub = FakeHub(connected=True)
    conf = {"screen_interval_min_sec": 300, "screen_interval_max_sec": 900}
    loop = ScreenLoop(hub, conf)
    await loop._tick()
    assert len(hub.sent) == 1
    assert hub.sent[0]["type"] == MSG_REQUEST_SCREENSHOT
    assert hub.sent[0].get("reason") == "timer"


def test_tick_skips_when_disconnected():
    asyncio.run(_tick_skips_when_disconnected())


async def _tick_skips_when_disconnected():
    hub = FakeHub(connected=False)
    conf = {"screen_interval_min_sec": 300, "screen_interval_max_sec": 900}
    loop = ScreenLoop(hub, conf)
    await loop._tick()
    assert hub.sent == []


def test_reads_interval_each_cycle_and_stops():
    asyncio.run(_reads_interval_each_cycle_and_stops())


async def _reads_interval_each_cycle_and_stops():
    hub = FakeHub(connected=True)
    conf: dict[str, Any] = {
        "screen_interval_min_sec": 1,
        "screen_interval_max_sec": 1,
    }
    loop = ScreenLoop(hub, conf)
    await loop.start()
    await asyncio.sleep(1.35)
    hub._connected = False
    await asyncio.sleep(1.35)
    await loop.stop()
    assert any(m["type"] == MSG_REQUEST_SCREENSHOT for m in hub.sent)
    assert loop._task is None


def test_interval_swap_and_clamp():
    hub = FakeHub()
    conf: dict[str, Any] = {
        "screen_interval_min_sec": 900,
        "screen_interval_max_sec": 300,
    }
    loop = ScreenLoop(hub, conf)
    lo, hi = loop._interval_bounds()
    assert lo == 300 and hi == 900
    conf["screen_interval_min_sec"] = "bad"
    conf["screen_interval_max_sec"] = None
    lo2, hi2 = loop._interval_bounds()
    assert lo2 == 300 and hi2 == 900
