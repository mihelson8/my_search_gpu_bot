"""
Tests for MAX Messenger bot client helpers and reply formatting.
"""

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from max_bot import (
    MaxApiClient,
    MaxApiError,
    build_reply_for_text,
    extract_targets,
    extract_text_from_update,
    format_term_html,
    handle_callback_payload,
    inline_keyboard,
    main_menu_keyboard,
    process_update,
    verify_webhook_secret,
)
from translator.models import TechTerm


SAMPLE_MESSAGE_CREATED = {
    "timestamp": 1739184000000,
    "message": {
        "recipient": {
            "chat_id": -100000000,
            "chat_type": "dialog",
            "user_id": 12345,
        },
        "timestamp": 1739184000000,
        "body": {"mid": "mid.TEST", "seq": 0, "text": "Привет"},
        "sender": {
            "user_id": 54321,
            "first_name": "User",
            "is_bot": False,
            "name": "User",
        },
    },
    "user_locale": "ru",
    "update_type": "message_created",
}


def test_extract_text_from_update():
    assert extract_text_from_update(SAMPLE_MESSAGE_CREATED) == "Привет"
    assert extract_text_from_update({"update_type": "message_created", "message": {}}) == ""


def test_extract_targets_dialog_prefers_user_id():
    chat_id, user_id = extract_targets(SAMPLE_MESSAGE_CREATED)
    assert chat_id is None
    assert user_id == 54321


def test_extract_targets_group_chat():
    update = {
        "update_type": "message_created",
        "message": {
            "recipient": {"chat_id": -42, "chat_type": "chat"},
            "sender": {"user_id": 7, "is_bot": False},
            "body": {"text": "hi"},
        },
    }
    chat_id, user_id = extract_targets(update)
    assert chat_id == -42
    assert user_id == 7


def test_extract_targets_bot_started():
    update = {
        "update_type": "bot_started",
        "chat_id": 99,
        "user": {"user_id": 11, "name": "Ivan"},
        "payload": "promo",
    }
    chat_id, user_id = extract_targets(update)
    assert chat_id == 99
    assert user_id == 11


def test_inline_keyboard_structure():
    kb = inline_keyboard([[{"type": "callback", "text": "A", "payload": "x"}]])
    assert kb[0]["type"] == "inline_keyboard"
    assert kb[0]["payload"]["buttons"][0][0]["payload"] == "x"


def test_format_term_html():
    term = TechTerm(
        id="hello_test",
        category="daily_dialogue",
        en="Hello",
        ru="Привет",
        zh="你好",
        pinyin="nǐ hǎo",
        definition_ru="Приветствие",
        definition_en="Greeting",
        definition_zh="问候",
        bua="Мэндээ",
    )
    html_text = format_term_html(term)
    assert "你好" in html_text
    assert "nǐ hǎo" in html_text
    assert "Мэндээ" in html_text


def test_build_reply_start_and_random():
    text, kb = asyncio.run(build_reply_for_text("/start"))
    assert "Переводчик" in text
    assert kb[0]["type"] == "inline_keyboard"

    text2, kb2 = asyncio.run(build_reply_for_text("/random"))
    assert "Путунхуа" in text2 or "English" in text2
    assert kb2


def test_build_reply_translate_known_term():
    text, kb = asyncio.run(build_reply_for_text("спасибо"))
    assert text
    assert "Спасибо" in text or "谢谢" in text or "Thank" in text or "Путунхуа" in text
    assert kb


def test_callback_show_term_and_quiz():
    text, _ = asyncio.run(handle_callback_payload("cmd:help", 1))
    assert "Справка" in text or "справка" in text.lower() or "MAX" in text

    # quiz answer path with fake ids should not crash
    text2, _ = asyncio.run(handle_callback_payload("quiz_ans:0:1:missing_id", 1))
    assert "Неверно" in text2 or "Верно" in text2 or "Некоррект" in text2


def test_verify_webhook_secret(monkeypatch):
    monkeypatch.setattr("max_bot.MAX_WEBHOOK_SECRET", "")
    assert verify_webhook_secret({}) is True

    monkeypatch.setattr("max_bot.MAX_WEBHOOK_SECRET", "secret123")
    assert verify_webhook_secret({"X-Max-Bot-Api-Secret": "secret123"}) is True
    assert verify_webhook_secret({"X-Max-Bot-Api-Secret": "wrong"}) is False


def test_max_api_client_send_message_headers():
    client = MaxApiClient("test-token", base_url="https://platform-api2.max.ru")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"message":{"body":{"mid":"1"}}}'
    mock_resp.json.return_value = {"message": {"body": {"mid": "1"}}}

    with patch("httpx.Client") as client_cls:
        instance = client_cls.return_value.__enter__.return_value
        instance.request.return_value = mock_resp
        result = client.send_message("hi", user_id=123)
        assert result["message"]["body"]["mid"] == "1"
        args, kwargs = instance.request.call_args
        assert args[0] == "POST"
        assert args[1].endswith("/messages")
        assert kwargs["headers"]["Authorization"] == "test-token"
        assert kwargs["params"]["user_id"] == 123
        assert "access_token" not in (kwargs.get("params") or {})


def test_max_api_client_error():
    client = MaxApiClient("bad", base_url="https://platform-api2.max.ru")
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "unauthorized"
    mock_resp.content = b"unauthorized"

    with patch("httpx.Client") as client_cls:
        instance = client_cls.return_value.__enter__.return_value
        instance.request.return_value = mock_resp
        with pytest.raises(MaxApiError) as exc:
            client.get_me()
        assert exc.value.status_code == 401


def test_process_update_skips_bot_messages():
    client = MagicMock()
    update = json.loads(json.dumps(SAMPLE_MESSAGE_CREATED))
    update["message"]["sender"]["is_bot"] = True
    asyncio.run(process_update(client, update))
    client.send_message.assert_not_called()


def test_process_update_sends_reply():
    client = MagicMock()
    asyncio.run(process_update(client, SAMPLE_MESSAGE_CREATED))
    assert client.send_message.called
    kwargs = client.send_message.call_args.kwargs
    assert kwargs.get("user_id") == 54321
    assert kwargs.get("chat_id") is None


def test_main_menu_keyboard_has_callbacks():
    kb = main_menu_keyboard()
    payloads = [
        btn["payload"]
        for row in kb[0]["payload"]["buttons"]
        for btn in row
    ]
    assert "cmd:random" in payloads
    assert "cmd:quiz" in payloads
