# -*- coding: utf-8 -*-
"""WebSocket hub for deskpet shell <-> brain.

Author: Grok Bot (Ideas Implementation).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from .protocol import (
    MSG_BRAIN_HELLO,
    MSG_SHELL_HELLO,
    decode,
    encode,
    make_msg,
)

try:
    from astrbot.api import logger  # injects plugin_tag for AstrBot formatters
except ImportError:  # unit tests outside AstrBot runtime
    logger = logging.getLogger("astrbot.plugin.dafeiyu_deskpet.ws_hub")

# Allow ~2MB base64 PNG (+ JSON overhead) in v1 screenshot frames.
_MAX_FRAME_BYTES = 4 * 1024 * 1024

Handler = Callable[[dict[str, Any]], Awaitable[None]]


class WsHub:
    """Localhost JSON WebSocket server; single preferred shell client."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 18765,
        *,
        kick_old: bool = True,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.kick_old = bool(kick_old)
        self._handler: Optional[Handler] = None
        self._client: Optional[ServerConnection] = None
        self._server: Optional[Server] = None
        self._lock = asyncio.Lock()
        self._started = False

    def set_handler(self, coro: Handler | None) -> None:
        self._handler = coro

    @property
    def connected(self) -> bool:
        return self._client is not None

    async def start(self) -> None:
        if self._started and self._server is not None:
            return
        self._server = await serve(
            self._on_connect,
            self.host,
            self.port,
            max_size=_MAX_FRAME_BYTES,
            ping_interval=20,
            ping_timeout=20,
        )
        self._started = True
        try:
            logger.info(
                "dafeiyu_deskpet ws hub listening on ws://%s:%s",
                self.host,
                self.port,
            )
        except Exception:
            pass

    async def stop(self) -> None:
        async with self._lock:
            client = self._client
            self._client = None
        if client is not None:
            try:
                await client.close(1001, "hub stopping")
            except Exception:
                pass
        server = self._server
        self._server = None
        self._started = False
        if server is not None:
            server.close()
            await server.wait_closed()
            try:
                logger.info("dafeiyu_deskpet ws hub stopped")
            except Exception:
                pass

    async def broadcast(self, msg: dict[str, Any]) -> None:
        client = self._client
        if client is None:
            return
        raw = encode(msg)
        try:
            await client.send(raw)
        except ConnectionClosed:
            async with self._lock:
                if self._client is client:
                    self._client = None
        except Exception as exc:
            logger.warning("dafeiyu_deskpet broadcast failed: %s", exc)

    async def _on_connect(self, ws: ServerConnection) -> None:
        async with self._lock:
            if self._client is not None:
                if self.kick_old:
                    old = self._client
                    self._client = None
                    try:
                        await old.close(1000, "replaced by new shell")
                    except Exception:
                        pass
                else:
                    try:
                        await ws.close(1008, "shell already connected")
                    except Exception:
                        pass
                    return
            self._client = ws
        logger.info("dafeiyu_deskpet shell connected")
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    # Binary frames reserved for future screenshot blobs.
                    continue
                try:
                    msg = decode(raw)
                except Exception as exc:
                    logger.warning("dafeiyu_deskpet invalid frame: %s", exc)
                    continue
                if msg.get("type") == MSG_SHELL_HELLO:
                    await ws.send(encode(make_msg(MSG_BRAIN_HELLO, ok=True)))
                handler = self._handler
                if handler is not None:
                    try:
                        await handler(msg)
                    except Exception as exc:
                        logger.error("dafeiyu_deskpet handler error: %s", exc)
        except ConnectionClosed:
            pass
        finally:
            async with self._lock:
                if self._client is ws:
                    self._client = None
            logger.info("dafeiyu_deskpet shell disconnected")
