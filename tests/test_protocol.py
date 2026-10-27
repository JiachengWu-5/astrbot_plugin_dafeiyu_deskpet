from core.protocol import make_msg, encode, decode, MSG_SCREEN_FEEDBACK

def test_screen_feedback_has_no_image_field_required():
    m = make_msg(MSG_SCREEN_FEEDBACK, text="摸摸头", to_qq=True)
    assert m["type"] == MSG_SCREEN_FEEDBACK
    assert m["text"] == "摸摸头"
    assert m["to_qq"] is True
    assert "image" not in m
    assert decode(encode(m))["text"] == "摸摸头"
