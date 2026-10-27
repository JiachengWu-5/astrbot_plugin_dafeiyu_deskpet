# -*- coding: utf-8 -*-
"""Unit tests: send_owner_text rejects image kwargs."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import qq_out


class _FakePlain:
    def __init__(self, text: str):
        self.text = text


class _FakeChain:
    def __init__(self):
        self.chain = []

    def message(self, text: str):
        self.chain.append(_FakePlain(text))
        return self


class _FakeContext:
    def __init__(self):
        self.sent = []
        self.platform_manager = SimpleNamespace(platform_insts=[])

    async def send_message(self, session, chain):
        self.sent.append((session, chain))


def test_send_owner_text_rejects_image_kwargs():
    ctx = _FakeContext()

    async def _run():
        with pytest.raises(TypeError) as ei:
            await qq_out.send_owner_text(
                ctx, "407171301", "hi", image_bytes=b"not-allowed"
            )
        assert "image" in str(ei.value).lower()

        with pytest.raises(TypeError):
            await qq_out.send_owner_text(ctx, "407171301", "hi", image="/tmp/x.png")

        with pytest.raises(TypeError):
            await qq_out.send_owner_text(ctx, "407171301", "hi", screenshot=b"x")

    asyncio.run(_run())
    assert ctx.sent == []


def test_send_owner_text_plain_only_happy_path(monkeypatch):
    monkeypatch.setattr(qq_out, "Plain", _FakePlain)
    monkeypatch.setattr(qq_out, "MessageChain", _FakeChain)
    monkeypatch.setattr(qq_out, "_resolve_platform_id", lambda ctx: "default")

    ctx = _FakeContext()

    async def _run():
        await qq_out.send_owner_text(ctx, "407171301", "摸摸头")

    asyncio.run(_run())
    assert len(ctx.sent) == 1
    session, chain = ctx.sent[0]
    assert session.endswith(":FriendMessage:407171301")
    assert all(isinstance(c, _FakePlain) for c in chain.chain)
    assert chain.chain[0].text == "摸摸头"
