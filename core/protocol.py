from __future__ import annotations
import json
from typing import Any

MSG_SHELL_HELLO = "shell.hello"
MSG_BRAIN_HELLO = "brain.hello"
MSG_REQUEST_SCREENSHOT = "brain.request_screenshot"
MSG_SCREENSHOT = "shell.screenshot"
MSG_USER_CHAT = "shell.user_chat"
MSG_REPLY = "brain.reply"
MSG_SCREEN_FEEDBACK = "brain.screen_feedback"
MSG_MIRROR_QQ = "brain.mirror_qq_reply"
MSG_EXPR = "brain.expr"

def make_msg(type_: str, **payload: Any) -> dict[str, Any]:
    out = {"type": type_, **payload}
    return out

def encode(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False)

def decode(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict) or "type" not in data:
        raise ValueError("invalid deskpet message")
    return data
