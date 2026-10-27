# -*- coding: utf-8 -*-
"""Dafeiyu deskpet brain (AstrBot Star).

Author: Grok Bot (Ideas Implementation).
"""
from __future__ import annotations

import asyncio
import base64
import binascii
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig

from .core.protocol import (
    MSG_SCREEN_FEEDBACK,
    MSG_SCREENSHOT,
    MSG_USER_CHAT,
    make_msg,
)
from .core.qq_out import send_owner_text
from .core.screen_loop import ScreenLoop
from .core import session_bridge
from .core.vision_feedback import feedback_from_image, qq_allowed_for_feedback
from .core.ws_hub import WsHub


def _decode_screenshot_payload(msg: dict[str, Any]) -> bytes | None:
    """Extract PNG bytes from shell.screenshot JSON (base64 fields only)."""
    for key in ("image_b64", "png_b64", "data", "image"):
        raw = msg.get(key)
        if not raw or not isinstance(raw, str):
            continue
        s = raw.strip()
        if s.startswith("data:") and "," in s:
            s = s.split(",", 1)[1]
        try:
            data = base64.b64decode(s, validate=False)
        except (binascii.Error, ValueError) as exc:
            logger.warning(
                "dafeiyu_deskpet screenshot b64 decode fail (%s): %s", key, exc
            )
            continue
        if not data:
            continue
        meta_len = msg.get("bytes_len")
        if meta_len is not None:
            try:
                expected = int(meta_len)
                if expected > 0 and abs(expected - len(data)) > 16:
                    logger.warning(
                        "dafeiyu_deskpet screenshot bytes_len mismatch: meta=%s actual=%s",
                        expected,
                        len(data),
                    )
            except (TypeError, ValueError):
                pass
        return data
    return None


class DafeiyuDeskpet(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.conf = config
        host = str(self.conf.get("ws_host") or "127.0.0.1")
        port = int(self.conf.get("ws_port") or 18765)
        self.hub = WsHub(host=host, port=port, kick_old=True)
        self.hub.set_handler(self._on_shell_msg)
        self.screen_loop = ScreenLoop(self.hub, self.conf)
        self._hub_task: asyncio.Task | None = None
        if bool(self.conf.get("enabled", True)):
            self._hub_task = asyncio.create_task(self._start_hub())
        logger.info("dafeiyu_deskpet loaded (ws hub on %s:%s)", host, port)

    async def _start_hub(self) -> None:
        try:
            await self.hub.start()
        except Exception as exc:
            logger.error("dafeiyu_deskpet ws hub start failed: %s", exc)
            return
        try:
            await self.screen_loop.start()
        except Exception as exc:
            logger.error("dafeiyu_deskpet screen loop start failed: %s", exc)

    async def _on_shell_msg(self, msg: dict[str, Any]) -> None:
        typ = msg.get("type")
        if typ == MSG_SCREENSHOT:
            await self._handle_screenshot(msg)
        elif typ == MSG_USER_CHAT:
            await self._handle_user_chat(msg)

    async def _handle_user_chat(self, msg: dict[str, Any]) -> None:
        """Shell local chat → shared LLM history → brain.reply only (never QQ)."""
        text = str(msg.get("text") or msg.get("content") or "").strip()
        if not text:
            return

        # CODE-LOCK: enable_shell_chat_to_qq is ignored; shell chat never hits QQ.
        if session_bridge.shell_chat_may_sync_to_qq(self.conf):
            logger.error(
                "dafeiyu_deskpet invariant broken: shell_chat_may_sync_to_qq True"
            )
            return

        try:
            reply = await session_bridge.chat_with_shared_history(
                self.context, self.conf, text
            )
        except Exception as exc:
            logger.error("dafeiyu_deskpet shell chat error: %s", exc)
            reply = "这会儿接不上话…你再发一句试试？"

        out = session_bridge.reply_msg(reply or "……")
        # Never call send_owner_text / qq_out here — even if conf toggled.
        try:
            await self.hub.broadcast(out)
        except Exception as exc:
            logger.error("dafeiyu_deskpet shell reply broadcast fail: %s", exc)

    async def _handle_screenshot(self, msg: dict[str, Any]) -> None:
        image_bytes = _decode_screenshot_payload(msg)
        if image_bytes is None:
            logger.warning("dafeiyu_deskpet screenshot missing/invalid image payload")
            return

        reason = str(msg.get("reason") or "")
        chat_history: list = []
        try:
            text = await feedback_from_image(
                self.context, self.conf, image_bytes, chat_history
            )
        except Exception as exc:
            logger.error("dafeiyu_deskpet feedback_from_image error: %s", exc)
            return

        # SKIP / nothing to say → silence both shell and QQ
        if not text:
            logger.info("dafeiyu_deskpet screen feedback SKIP (reason=%s)", reason)
            return

        # Design: vision failure apology -> shell only; qq_allowed_for_feedback never True for apology.
        to_qq = qq_allowed_for_feedback(text)
        await self.hub.broadcast(
            make_msg(MSG_SCREEN_FEEDBACK, text=text, to_qq=bool(to_qq), reason=reason)
        )

        if to_qq:
            qq_uid = str(self.conf.get("qq_uid") or "").strip()
            if not qq_uid:
                logger.warning("dafeiyu_deskpet qq_uid empty; skip QQ send")
                return
            # Do not block the WS handler on NapCat/QQ latency.
            asyncio.create_task(self._send_qq_safe(qq_uid, text))

    async def _send_qq_safe(self, qq_uid: str, text: str) -> None:
        try:
            await send_owner_text(self.context, qq_uid, text)
        except Exception as exc:
            logger.error(
                "dafeiyu_deskpet QQ send failed (shell already bubbled): %s", exc
            )

    @filter.on_decorating_result(priority=50)
    async def mirror_qq_reply_to_shell(self, event: AstrMessageEvent) -> None:
        """Observe outbound bot reply (before send) and mirror Plain text to shell.

        Does not send/duplicate QQ — pipeline still delivers the original result.
        Hook found via AstrBot EventType.OnDecoratingResultEvent /
        @filter.on_decorating_result (same pattern as dafeiyu_clean / GPT_SoVITS).
        """
        if not bool(self.conf.get("enabled", True)):
            return
        if not bool(self.conf.get("enable_qq_mirror_to_shell", True)):
            return
        try:
            if not event.is_private_chat():
                return
        except Exception:
            return

        owner = str(self.conf.get("qq_uid") or "").strip()
        if owner:
            try:
                sid = str(event.get_sender_id() or "")
            except Exception:
                sid = ""
            if sid and sid != owner:
                return

        try:
            result = event.get_result()
        except Exception:
            return
        text = session_bridge.extract_plain_from_result(result)
        if not text:
            return

        try:
            await self.hub.broadcast(session_bridge.mirror_msg(text))
        except Exception as exc:
            logger.warning("dafeiyu_deskpet mirror_qq_reply broadcast fail: %s", exc)

    async def terminate(self):
        try:
            await self.screen_loop.stop()
        except Exception as exc:
            logger.warning("dafeiyu_deskpet screen loop stop: %s", exc)
        if self._hub_task is not None and not self._hub_task.done():
            self._hub_task.cancel()
            try:
                await self._hub_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            self._hub_task = None
        try:
            await self.hub.stop()
        except Exception as exc:
            logger.warning("dafeiyu_deskpet ws hub stop: %s", exc)
