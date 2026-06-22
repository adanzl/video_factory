from app.services.llm.deepseek_request import build_deepseek_chat_payload


def test_build_deepseek_chat_payload_disables_thinking_by_default():
    payload = build_deepseek_chat_payload(
        model="deepseek-v4-flash",
        system="sys",
        user="usr",
        max_tokens=1024,
        thinking_enabled=False,
    )
    assert payload["thinking"] == {"type": "disabled"}


def test_build_deepseek_chat_payload_can_enable_thinking():
    payload = build_deepseek_chat_payload(
        model="deepseek-v4-pro",
        system="sys",
        user="usr",
        max_tokens=1024,
        thinking_enabled=True,
    )
    assert payload["thinking"] == {"type": "enabled"}
