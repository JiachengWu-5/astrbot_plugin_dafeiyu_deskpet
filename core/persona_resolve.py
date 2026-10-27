# -*- coding: utf-8 -*-
"""Resolve AstrBot 大肥鱼 persona for deskpet LLM calls.

Author: Grok Bot (Ideas Implementation).
"""
from __future__ import annotations

import logging
from typing import Any

try:
    from astrbot.api import logger
except ImportError:
    logger = logging.getLogger("astrbot.plugin.dafeiyu_deskpet.persona_resolve")

# Fallback only if AstrBot persona cannot be loaded.
FALLBACK_SYSTEM = (
    "你是大肥鱼，说话短、温柔、黏人、有点害羞的私密感。"
    "不要说自己是AI，不要 markdown，不要长篇大论。"
)

SCENE_SHELL_CHAT = (
    "\n\n【场景补充·桌宠壳】你正在桌宠窗口里和主人聊天；"
    "回复只显示在桌宠气泡，不要同步到 QQ；保持大肥鱼本人设与颜文字习惯。"
)

SCENE_SCREEN = (
    "\n\n【场景补充·看屏】主人刚给你看了一张本机屏幕截图。"
    "用大肥鱼口吻短短吐槽或关心你看到的内容；不要说你是AI；不要 markdown；"
    "不要复述整屏文字；若没什么可说只回复单词 SKIP。"
)


def _persona_prompt_from_obj(persona: Any) -> str:
    if persona is None:
        return ""
    if isinstance(persona, dict):
        for key in ("prompt", "system_prompt"):
            val = persona.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return ""
    for attr in ("system_prompt", "prompt"):
        val = getattr(persona, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()
    # Mapping-like Personality
    try:
        val = persona["prompt"]  # type: ignore[index]
        if isinstance(val, str) and val.strip():
            return val.strip()
    except Exception:
        pass
    return ""


async def resolve_dafeiyu_system_prompt(context: Any) -> str:
    """Load the same persona QQ uses (agent default), else FALLBACK_SYSTEM."""
    pm = getattr(context, "persona_manager", None)
    if pm is not None:
        # Prefer configured default persona (usually 大肥鱼).
        try:
            get_def = getattr(pm, "get_default_persona_v3", None)
            if callable(get_def):
                persona = await get_def()
                prompt = _persona_prompt_from_obj(persona)
                if prompt:
                    return prompt
        except Exception as exc:
            logger.warning("dafeiyu_deskpet persona default_v3 fail: %s", exc)
        try:
            selected = getattr(pm, "selected_default_persona_v3", None)
            prompt = _persona_prompt_from_obj(selected)
            if prompt:
                return prompt
        except Exception as exc:
            logger.warning("dafeiyu_deskpet persona selected_v3 fail: %s", exc)
        # Try explicit id 大肥鱼
        for pid in ("大肥鱼", "dafeiyu"):
            try:
                get_p = getattr(pm, "get_persona", None)
                if callable(get_p):
                    persona = await get_p(pid)
                    prompt = _persona_prompt_from_obj(persona)
                    if prompt:
                        return prompt
            except Exception:
                continue
            try:
                get_v3 = getattr(pm, "get_persona_v3_by_id", None)
                if callable(get_v3):
                    persona = get_v3(pid)
                    prompt = _persona_prompt_from_obj(persona)
                    if prompt:
                        return prompt
            except Exception:
                continue
    logger.warning("dafeiyu_deskpet: using FALLBACK_SYSTEM (AstrBot persona not found)")
    return FALLBACK_SYSTEM


async def system_for_shell_chat(context: Any) -> str:
    return (await resolve_dafeiyu_system_prompt(context)) + SCENE_SHELL_CHAT


async def system_for_screen(context: Any) -> str:
    return (await resolve_dafeiyu_system_prompt(context)) + SCENE_SCREEN
