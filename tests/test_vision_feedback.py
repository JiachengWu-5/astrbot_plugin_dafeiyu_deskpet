# -*- coding: utf-8 -*-
"""Unit tests: vision SKIP path + failure apology never QQ + temp cleanup."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.vision_feedback import (
    APOLOGY_TEXT,
    feedback_from_image,
    is_failure_apology,
    qq_allowed_for_feedback,
    reset_failure_burst_for_tests,
)


class _FakeResp:
    def __init__(self, text: str):
        self.completion_text = text


class _FakeProvider:
    def __init__(self, text: str):
        self.text = text
        self.calls = []
        self.seen_paths = []

    async def text_chat(self, **kwargs):
        self.calls.append(kwargs)
        urls = kwargs.get("image_urls") or []
        self.seen_paths.extend(urls)
        for p in urls:
            # Path must exist during the call.
            assert Path(p).is_file(), f"missing temp during call: {p}"
        return _FakeResp(self.text)


class _FakeContext:
    def __init__(self, provider=None):
        self._provider = provider

    def get_using_provider(self):
        return self._provider


def test_skip_literal_returns_none_and_deletes_temp():
    reset_failure_burst_for_tests()
    provider = _FakeProvider("SKIP")
    ctx = _FakeContext(provider)
    conf = {"skip_if_nothing_to_say": True}
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

    async def _run():
        return await feedback_from_image(ctx, conf, png, [])

    out = asyncio.run(_run())
    assert out is None
    assert len(provider.calls) == 1
    # Temp deleted after return
    for p in provider.seen_paths:
        assert not Path(p).exists()


def test_no_provider_returns_apology_shell_only_never_qq():
    reset_failure_burst_for_tests()
    ctx = _FakeContext(None)
    conf = {"skip_if_nothing_to_say": True}
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8

    async def _run():
        return await feedback_from_image(ctx, conf, png, [])

    out = asyncio.run(_run())
    assert out == APOLOGY_TEXT
    assert is_failure_apology(out)
    # Design: failure apology may bubble to shell, NEVER to QQ
    assert qq_allowed_for_feedback(out) is False
    assert qq_allowed_for_feedback(out) is False  # still never


def test_empty_bytes_apology_never_qq():
    reset_failure_burst_for_tests()
    ctx = _FakeContext(_FakeProvider("should-not-run"))
    conf = {"skip_if_nothing_to_say": True}

    async def _run():
        return await feedback_from_image(ctx, conf, b"", [])

    out = asyncio.run(_run())
    assert out == APOLOGY_TEXT
    assert qq_allowed_for_feedback(out) is False


def test_provider_typeerror_apology_never_qq():
    reset_failure_burst_for_tests()

    class BadProvider:
        async def text_chat(self, **kwargs):
            raise TypeError("image_urls unexpected")

    ctx = _FakeContext(BadProvider())
    conf = {"skip_if_nothing_to_say": True}
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8

    async def _run():
        return await feedback_from_image(ctx, conf, png, [])

    out = asyncio.run(_run())
    assert out == APOLOGY_TEXT
    assert qq_allowed_for_feedback(out) is False


def test_normal_text_allows_qq():
    reset_failure_burst_for_tests()
    assert qq_allowed_for_feedback(None) is False
    assert qq_allowed_for_feedback("") is False
    assert qq_allowed_for_feedback("你这会儿在写代码呀～") is True
    # Apology still never, even after success text
    assert qq_allowed_for_feedback(APOLOGY_TEXT) is False
