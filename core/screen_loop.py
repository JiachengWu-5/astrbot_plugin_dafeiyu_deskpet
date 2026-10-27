# -*- coding: utf-8 -*-
"""Random-interval screen look scheduler for deskpet brain.

Author: Grok Bot (Ideas Implementation).
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Mapping, MutableMapping, Optional, Protocol

from .protocol import MSG_REQUEST_SCREENSHOT, make_msg

try:
    from astrbot.api import logger
except ImportError:  # unit tests outside AstrBot runtime
    logger = logging.getLogger("astrbot.plugin.dafeiyu_deskpet.screen_loop")


class _HubLike(Protocol):
    @property
    def connected(self) -> bool: ...

    async def broadcast(self, msg: dict[str, Any]) -> None: ...


class ScreenLoop:
    """Sleep random [min,max] from conf each cycle; request screenshot if shell connected."""

    def __init__(
        self,
        hub: _HubLike,
        conf: Mapping[str, Any] | MutableMapping[str, Any],
        *,
        reason: str = "timer",
    ) -> None:
        self.hub = hub
        self.conf = conf
        self.reason = reason
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    def _interval_bounds(self) -> tuple[int, int]:
        try:
            lo = int(self.conf.get("screen_interval_min_sec") or 300)
        except (TypeError, ValueError):
            lo = 300
        try:
            hi = int(self.conf.get("screen_interval_max_sec") or 900)
        except (TypeError, ValueError):
            hi = 900
        if lo < 1:
            lo = 1
        if hi < 1:
            hi = 1
        if hi < lo:
            lo, hi = hi, lo
        return lo, hi

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="dafeiyu_screen_loop")
        try:
            logger.info("dafeiyu_deskpet screen loop started")
        except Exception:
            pass

    async def stop(self) -> None:
        self._stop.set()
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        try:
            logger.info("dafeiyu_deskpet screen loop stopped")
        except Exception:
            pass

    async def _run(self) -> None:
        while not self._stop.is_set():
            lo, hi = self._interval_bounds()
            delay = random.randint(lo, hi)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=float(delay))
                break
            except asyncio.TimeoutError:
                pass
            if self._stop.is_set():
                break
            await self._tick()

    async def _tick(self) -> None:
        if self.hub.connected:
            try:
                await self.hub.broadcast(
                    make_msg(MSG_REQUEST_SCREENSHOT, reason=self.reason)
                )
            except Exception as exc:
                try:
                    logger.warning(
                        "dafeiyu_deskpet screen loop broadcast failed: %s", exc
                    )
                except Exception:
                    pass
                return
            try:
                logger.info(
                    "dafeiyu_deskpet screen loop requested screenshot (reason=%s)",
                    self.reason,
                )
            except Exception:
                pass
        else:
            try:
                logger.info(
                    "dafeiyu_deskpet screen loop skip: shell not connected (no QQ)"
                )
            except Exception:
                pass
