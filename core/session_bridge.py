# -*- coding: utf-8 -*-
"""Shared conversation bridge between deskpet shell chat and QQ owner.

Author: Grok Bot (Ideas Implementation).
"""
from __future__ import annotations

import json
import logging
from typing import Any

try:
    from astrbot.api import logger
except ImportError:  # unit tests outside AstrBot runtime
    logger = logging.getLogger("astrbot.plugin.dafeiyu_deskpet.session_bridge")

from .qq_out import owner_session
from .persona_resolve import system_for_shell_chat

DEFAULT_SYSTEM = (
    "你是大肥鱼，说话短、温柔、黏人、有点害羞的私密感。"
    "不要说自己是AI，不要 markdown，不要长篇大论。"
    "你正在桌宠壳里和主人聊天；回复会显示在桌宠气泡里，不会同步到 QQ。"
)

# Hard privacy: shell chat must NEVER sync to QQ, even if config toggled.
SHELL_CHAT_TO_QQ_LOCKED_FALSE = True


def shell_chat_may_sync_to_qq(conf: Any) -> bool:
    """Always False — code-lock; config enable_shell_chat_to_qq is ignored."""
    _ = conf  # intentionally unused; lock overrides any config
    return False


def extract_plain_from_result(result: Any) -> str:
    """Collect Plain text from an AstrBot MessageEventResult (or duck-typed)."""
    if result is None:
        return ""
    chain = getattr(result, "chain", None)
    if not chain:
        return ""
    parts: list[str] = []
    for comp in chain:
        text = getattr(comp, "text", None)
        if text is None and isinstance(comp, dict):
            text = comp.get("text")
        if text is None:
            continue
        s = str(text).strip()
        if s:
            parts.append(s)
    return "\n".join(parts).strip()


def mirror_msg(text: str) -> dict[str, Any]:
    """Shape for brain.mirror_qq_reply (shell bubble only)."""
    from .protocol import MSG_MIRROR_QQ, make_msg

    body = (text or "").strip()
    return make_msg(MSG_MIRROR_QQ, text=body)


def reply_msg(text: str) -> dict[str, Any]:
    """Shape for brain.reply — to_qq forced false."""
    from .protocol import MSG_REPLY, make_msg

    body = (text or "").strip()
    return make_msg(MSG_REPLY, text=body, to_qq=False)


def _parse_history(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = item.get("content")
        if role not in ("user", "assistant", "system"):
            continue
        if content is None:
            continue
        if isinstance(content, str):
            c = content
        else:
            c = str(content)
        if not c.strip() and role != "assistant":
            continue
        out.append({"role": role, "content": c})
    return out


async def get_owner_conversation_id(context: Any, qq_uid: str) -> str | None:
    umo = owner_session(context, qq_uid)
    cm = getattr(context, "conversation_manager", None)
    if cm is None:
        return None
    try:
        return await cm.get_curr_conversation_id(umo)
    except Exception as exc:
        logger.warning("dafeiyu_deskpet session_bridge get cid fail: %s", exc)
        return None


async def load_shared_contexts(
    context: Any,
    qq_uid: str,
    *,
    max_messages: int = 24,
) -> tuple[str | None, str, list[dict[str, Any]]]:
    """Return (cid, umo, openai-style message dicts) for owner QQ session."""
    umo = owner_session(context, qq_uid)
    cm = getattr(context, "conversation_manager", None)
    if cm is None:
        return None, umo, []
    try:
        cid = await cm.get_curr_conversation_id(umo)
    except Exception as exc:
        logger.warning("dafeiyu_deskpet session_bridge cid fail: %s", exc)
        return None, umo, []
    if not cid:
        return None, umo, []
    try:
        conv = await cm.get_conversation(umo, cid)
    except Exception as exc:
        logger.warning("dafeiyu_deskpet session_bridge get_conversation fail: %s", exc)
        return cid, umo, []
    if conv is None:
        return cid, umo, []
    hist = _parse_history(getattr(conv, "history", None))
    if max_messages > 0 and len(hist) > max_messages:
        hist = hist[-max_messages:]
    return cid, umo, hist


async def append_shell_turn(
    context: Any,
    qq_uid: str,
    user_text: str,
    assistant_text: str,
) -> None:
    """Persist shell chat turn into shared owner conversation (no QQ send)."""
    user_body = (user_text or "").strip()
    asst_body = (assistant_text or "").strip()
    if not user_body or not asst_body:
        return
    cm = getattr(context, "conversation_manager", None)
    if cm is None:
        return
    cid, _umo, _hist = await load_shared_contexts(context, qq_uid, max_messages=0)
    if not cid:
        try:
            umo = owner_session(context, qq_uid)
            cid = await cm.new_conversation(umo)
        except Exception as exc:
            logger.warning(
                "dafeiyu_deskpet session_bridge new_conversation fail: %s", exc
            )
            return
    try:
        await cm.add_message_pair(
            cid,
            {"role": "user", "content": user_body},
            {"role": "assistant", "content": asst_body},
        )
    except Exception as exc:
        logger.warning("dafeiyu_deskpet session_bridge add_message_pair fail: %s", exc)


async def _pick_provider(context: Any):
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


async def chat_with_shared_history(
    context: Any,
    conf: Any,
    user_text: str,
    *,
    system_prompt: str | None = None,
) -> str | None:
    """LLM reply using owner QQ shared history. Never sends to QQ."""
    prompt = (user_text or "").strip()
    if not prompt:
        return None

    # Code-lock checked for clarity; always False.
    assert shell_chat_may_sync_to_qq(conf) is False

    qq_uid = str(conf.get("qq_uid") or "").strip()
    contexts: list[dict[str, Any]] = []
    if qq_uid:
        _cid, _umo, contexts = await load_shared_contexts(context, qq_uid)

    provider = await _pick_provider(context)
    if provider is None or not hasattr(provider, "text_chat"):
        logger.warning("dafeiyu_deskpet shell chat: no LLM provider")
        return "这会儿脑子有点懵，你等下再跟我说一句好不好…"

    sys_p = system_prompt if system_prompt is not None else await system_for_shell_chat(context)
    try:
        resp = await provider.text_chat(
            system_prompt=sys_p,
            prompt=prompt,
            contexts=contexts or None,
        )
    except Exception as exc:
        logger.error("dafeiyu_deskpet shell chat LLM fail: %s", exc)
        return "这会儿接不上话…你再发一句试试？"

    raw = getattr(resp, "completion_text", None) if resp is not None else None
    if isinstance(resp, str):
        raw = resp
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("text"):
            text = text[4:].lstrip()
        text = text.strip()
    if not text:
        return None

    if qq_uid:
        try:
            await append_shell_turn(context, qq_uid, prompt, text)
        except Exception as exc:
            logger.warning(
                "dafeiyu_deskpet shell chat history append fail: %s", exc
            )
    return text
