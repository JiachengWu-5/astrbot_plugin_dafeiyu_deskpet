# -*- coding: utf-8 -*-
"""Unit tests: shell chat never qq_out; mirror message shape."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import session_bridge
from core.protocol import MSG_MIRROR_QQ, MSG_REPLY


class _FakePlain:
    def __init__(self, text: str):
        self.text = text


class _FakeResult:
    def __init__(self, texts: list[str]):
        self.chain = [_FakePlain(t) for t in texts]


class _RecordingProvider:
    def __init__(self, reply: str = "摸摸头~"):
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    async def text_chat(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(completion_text=self.reply)


class _FakeCM:
    def __init__(self):
        self.pairs: list[tuple] = []
        self._cid = "cid-test-1"
        self._history = [
            {"role": "user", "content": "之前QQ说过的"},
            {"role": "assistant", "content": "嗯嗯我记得"},
        ]

    async def get_curr_conversation_id(self, umo):
        return self._cid

    async def get_conversation(self, umo, cid):
        import json

        return SimpleNamespace(history=json.dumps(self._history), cid=cid)

    async def new_conversation(self, umo):
        return self._cid

    async def add_message_pair(self, cid, user_message, assistant_message):
        self.pairs.append((cid, user_message, assistant_message))
        self._history.append(user_message)
        self._history.append(assistant_message)


class _FakeContext:
    def __init__(self, provider=None):
        self.conversation_manager = _FakeCM()
        self._provider = provider or _RecordingProvider()
        self.platform_manager = SimpleNamespace(platform_insts=[])
        self.qq_out_calls: list[tuple] = []

    def get_using_provider(self):
        return self._provider


class _FakeHub:
    def __init__(self):
        self.broadcasts: list[dict] = []

    async def broadcast(self, msg: dict):
        self.broadcasts.append(msg)


class _FakeConf(dict):
    def get(self, key, default=None):
        return super().get(key, default)


def test_shell_chat_may_sync_locked_false_even_if_config_true():
    conf = _FakeConf(enable_shell_chat_to_qq=True, qq_uid="407171301")
    assert session_bridge.shell_chat_may_sync_to_qq(conf) is False
    assert session_bridge.SHELL_CHAT_TO_QQ_LOCKED_FALSE is True


def test_mirror_msg_shape():
    m = session_bridge.mirror_msg("从QQ来的回复")
    assert m["type"] == MSG_MIRROR_QQ
    assert m["text"] == "从QQ来的回复"
    assert "to_qq" not in m or m.get("to_qq") is not True


def test_reply_msg_to_qq_forced_false():
    m = session_bridge.reply_msg("壳里聊")
    assert m["type"] == MSG_REPLY
    assert m["text"] == "壳里聊"
    assert m["to_qq"] is False


def test_extract_plain_from_result():
    r = _FakeResult(["你好", "第二段"])
    assert session_bridge.extract_plain_from_result(r) == "你好\n第二段"
    assert session_bridge.extract_plain_from_result(None) == ""
    assert session_bridge.extract_plain_from_result(SimpleNamespace(chain=[])) == ""


def test_shell_chat_path_never_calls_qq_out(monkeypatch):
    """chat_with_shared_history must not import/call qq_out.send_owner_text."""
    provider = _RecordingProvider("壳里回你啦")
    ctx = _FakeContext(provider)
    conf = _FakeConf(qq_uid="407171301", enable_shell_chat_to_qq=True)

    qq_calls: list = []

    async def _boom(*a, **k):
        qq_calls.append((a, k))
        raise AssertionError("qq_out must not be called from shell chat")

    # If anything tries send_owner_text, fail hard.
    import core.qq_out as qq_out

    monkeypatch.setattr(qq_out, "send_owner_text", _boom)
    monkeypatch.setattr(
        session_bridge, "owner_session", lambda context, qq_uid: f"default:FriendMessage:{qq_uid}"
    )

    async def _run():
        text = await session_bridge.chat_with_shared_history(ctx, conf, "在干嘛")
        return text

    reply = asyncio.run(_run())
    assert reply == "壳里回你啦"
    assert qq_calls == []
    assert len(provider.calls) == 1
    # shared history was passed
    assert provider.calls[0].get("contexts")
    # history append happened (shared context), still no QQ send
    assert len(ctx.conversation_manager.pairs) == 1


def test_handle_user_chat_handler_never_qq(monkeypatch):
    """Simulate main._handle_user_chat: broadcast reply, never qq_out."""
    hub = _FakeHub()
    qq_calls: list = []

    async def _boom(*a, **k):
        qq_calls.append((a, k))
        raise AssertionError("qq_out must not be called")

    import core.qq_out as qq_out

    monkeypatch.setattr(qq_out, "send_owner_text", _boom)

    async def fake_chat(context, conf, user_text, **kwargs):
        return f"echo:{user_text}"

    monkeypatch.setattr(session_bridge, "chat_with_shared_history", fake_chat)

    conf = _FakeConf(qq_uid="407171301", enable_shell_chat_to_qq=True)
    ctx = _FakeContext()

    async def _handle_user_chat(msg: dict):
        # Mirrors main.py contract
        if session_bridge.shell_chat_may_sync_to_qq(conf):
            raise AssertionError("lock broken")
        text = str(msg.get("text") or msg.get("content") or "").strip()
        if not text:
            return
        reply = await session_bridge.chat_with_shared_history(ctx, conf, text)
        out = session_bridge.reply_msg(reply or "……")
        # CODE-LOCK: never qq_out regardless of enable_shell_chat_to_qq
        await hub.broadcast(out)

    asyncio.run(_handle_user_chat({"type": "shell.user_chat", "text": "你好呀"}))
    assert qq_calls == []
    assert len(hub.broadcasts) == 1
    b = hub.broadcasts[0]
    assert b["type"] == MSG_REPLY
    assert b["to_qq"] is False
    assert b["text"] == "echo:你好呀"
