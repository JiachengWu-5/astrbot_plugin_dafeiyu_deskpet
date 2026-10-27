# -*- coding: utf-8 -*-
"""Screen-feedback via vision LLM; never attaches image to QQ.

Author: Grok Bot (Ideas Implementation).
"""
from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

try:
    from astrbot.api import logger
except ImportError:  # unit tests outside AstrBot runtime
    logger = logging.getLogger("astrbot.plugin.dafeiyu_deskpet.vision_feedback")

APOLOGY_TEXT = "这会儿看不清屏幕呀，等我眨眨眼再看～"
_SKIP_TOKENS = frozenset({"SKIP", "skip", "略", "没什么", "没话说"})

from .persona_resolve import system_for_screen

DEFAULT_SYSTEM = (
    "你是大肥鱼，说话短、软、口语化，像朋友私聊。"
    "用户发来一张本机屏幕截图，请用一两句短吐槽或关心回应你看到的内容。"
    "不要说「作为AI」，不要 markdown，不要复述整屏文字。"
    "如果画面无聊、看不清、或没什么值得说的，只回复字面量 SKIP（不要其它字）。"
)


def is_failure_apology(text: str | None) -> bool:
    return bool(text) and text.strip() == APOLOGY_TEXT


def qq_allowed_for_feedback(text: str | None) -> bool:
    """Whether this feedback text may be sent to QQ.

    Design (user 2026-10-27): vision/provider failure apology → deskpet only, NEVER QQ.
    - None / empty: no
    - Failure apology: never
    - Normal success text: yes
    """
    if not text or not str(text).strip():
        return False
    if is_failure_apology(text):
        return False
    return True


def reset_failure_burst_for_tests() -> None:
    """Kept for test API compatibility; no-op after design fix (no QQ burst state)."""
    return None


def _skip_enabled(conf: Any) -> bool:
    try:
        return bool(conf.get("skip_if_nothing_to_say", True))
    except Exception:
        return True


def _normalize_result(raw: str | None, *, skip_ok: bool) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("text"):
            text = text[4:].lstrip()
        text = text.strip()
    upper = text.upper()
    if skip_ok and (upper == "SKIP" or text in _SKIP_TOKENS):
        return None
    if skip_ok and upper.startswith("SKIP") and len(text) <= 8:
        return None
    return text or None


async def _pick_provider(context: Any):
    """Best-effort: using provider, else None."""
    provider = None
    try:
        provider = context.get_using_provider()
    except Exception:
        provider = None
    if provider is not None:
        return provider
    try:
        get_async = getattr(context, "get_using_provider_async", None)
        if callable(get_async):
            provider = await get_async()
    except Exception:
        provider = None
    return provider


async def feedback_from_image(
    context: Any,
    conf: Any,
    image_bytes: bytes,
    chat_history: list,
) -> str | None:
    """Run vision LLM on screenshot bytes; return feedback text or None to skip.

    Hard rules:
    - Never send the image to QQ (caller uses qq_out Plain-only).
    - Always delete temp files after use.
    - If no usable vision provider: return short apology for shell only
      (caller must not QQ — qq_allowed_for_feedback returns False).
    """
    skip_ok = _skip_enabled(conf)
    if not image_bytes:
        return APOLOGY_TEXT

    provider = await _pick_provider(context)
    if provider is None or not hasattr(provider, "text_chat"):
        logger.warning("dafeiyu_deskpet vision: no LLM provider")
        return APOLOGY_TEXT

    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix="dafeiyu_deskpet_", suffix=".png")
        os.close(fd)
        with open(tmp_path, "wb") as f:
            f.write(image_bytes)

        hist_hint = ""
        if chat_history:
            bits = []
            for item in chat_history[-6:]:
                if isinstance(item, dict):
                    role = str(item.get("role") or "")
                    content = str(item.get("content") or item.get("text") or "").strip()
                    if content:
                        bits.append(f"{role}: {content[:80]}")
                elif isinstance(item, str) and item.strip():
                    bits.append(item.strip()[:80])
            if bits:
                hist_hint = "最近聊天摘要：\n" + "\n".join(bits)

        prompt = "看看我屏幕现在在干嘛，用大肥鱼语气说一两句。"
        if hist_hint:
            prompt = hist_hint + "\n\n" + prompt
        if skip_ok:
            prompt += "\n若没什么可说，只回复 SKIP。"

        try:
            resp = await provider.text_chat(
                system_prompt=await system_for_screen(context),
                prompt=prompt,
                image_urls=[tmp_path],
            )
        except TypeError:
            logger.warning("dafeiyu_deskpet vision: provider lacks image_urls support")
            return APOLOGY_TEXT
        except Exception as exc:
            logger.error("dafeiyu_deskpet vision LLM fail: %s", exc)
            return APOLOGY_TEXT

        raw = getattr(resp, "completion_text", None) if resp is not None else None
        if isinstance(resp, str):
            raw = resp
        return _normalize_result(raw, skip_ok=skip_ok)
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except FileNotFoundError:
                pass
            except Exception as exc:
                logger.warning("dafeiyu_deskpet vision temp delete fail: %s", exc)
