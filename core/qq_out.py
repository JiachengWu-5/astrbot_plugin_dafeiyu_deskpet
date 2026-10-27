# -*- coding: utf-8 -*-
"""Send plain text to owner QQ only (never images).

Author: Grok Bot (Ideas Implementation).
"""
from __future__ import annotations

import logging
from typing import Any

try:
    from astrbot.core.message.components import Plain
    from astrbot.core.message.message_event_result import MessageChain
    from astrbot.core.platform.message_type import MessageType
except ImportError:  # unit tests outside AstrBot runtime
    Plain = None  # type: ignore[misc, assignment]
    MessageChain = None  # type: ignore[misc, assignment]
    MessageType = None  # type: ignore[misc, assignment]

try:
    from astrbot.api import logger
except ImportError:  # unit tests outside AstrBot runtime
    logger = logging.getLogger("astrbot.plugin.dafeiyu_deskpet.qq_out")

_FORBIDDEN_KW = frozenset(
    {
        "image",
        "images",
        "image_url",
        "image_urls",
        "image_path",
        "image_paths",
        "image_bytes",
        "png",
        "screenshot",
        "file_image",
        "url_image",
        "chain",
        "message_chain",
        "components",
    }
)


def _reject_forbidden_kwargs(kwargs: dict[str, Any]) -> None:
    if not kwargs:
        return
    bad = sorted(k for k in kwargs if k in _FORBIDDEN_KW or "image" in k.lower())
    if bad:
        raise TypeError(
            f"send_owner_text rejects image/media kwargs: {bad} "
            "(screenshots must never go to QQ)"
        )
    raise TypeError(f"send_owner_text got unexpected kwargs: {sorted(kwargs)}")


def _resolve_platform_id(context: Any) -> str:
    """Prefer the running aiocqhttp adapter id (this install uses id=default)."""
    try:
        pm = getattr(context, "platform_manager", None)
        platforms = getattr(pm, "platform_insts", None)
        if platforms is None:
            get_insts = getattr(pm, "get_insts", None)
            platforms = get_insts() if callable(get_insts) else []
        for p in platforms or []:
            meta = p.meta() if hasattr(p, "meta") else None
            if meta is None:
                continue
            name = str(getattr(meta, "name", "") or "")
            typ = str(getattr(meta, "type", "") or "")
            pid = str(getattr(meta, "id", "") or "")
            if name == "aiocqhttp" or typ == "aiocqhttp" or "aiocqhttp" in pid.lower():
                return pid or "aiocqhttp"
        for p in platforms or []:
            meta = p.meta() if hasattr(p, "meta") else None
            if meta is None:
                continue
            pid = str(getattr(meta, "id", "") or "")
            name = str(getattr(meta, "name", "") or "")
            if pid and name not in ("webchat",) and (name == "aiocqhttp" or pid == "default"):
                return pid
    except Exception as exc:
        logger.warning("dafeiyu_deskpet qq_out platform resolve failed: %s", exc)
    return "default"


def owner_session(context: Any, qq_uid: str) -> str:
    uid = str(qq_uid or "").strip()
    if not uid:
        raise ValueError("qq_uid required")
    mt = "FriendMessage"
    if MessageType is not None:
        mt = MessageType.FRIEND_MESSAGE.value
    return f"{_resolve_platform_id(context)}:{mt}:{uid}"


async def send_owner_text(context: Any, qq_uid: str, text: str, **kwargs: Any) -> None:
    """Send Plain-only private text to owner QQ. Never attaches images."""
    _reject_forbidden_kwargs(kwargs)

    body = (text or "").strip()
    if not body:
        return

    if MessageChain is None or Plain is None:
        raise RuntimeError("AstrBot MessageChain/Plain unavailable")

    session = owner_session(context, qq_uid)
    chain = MessageChain().message(body)
    for comp in list(chain.chain or []):
        if not isinstance(comp, Plain):
            raise TypeError(
                f"send_owner_text internal chain must be Plain-only, got {type(comp)}"
            )

    try:
        await context.send_message(session, chain)
        logger.info(
            "dafeiyu_deskpet qq_out sent plain to %s (%d chars)", qq_uid, len(body)
        )
    except Exception as exc:
        logger.error("dafeiyu_deskpet qq_out send failed to %s: %s", qq_uid, exc)
        raise
