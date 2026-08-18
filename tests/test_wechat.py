"""
Tests for WeChat Official Account Webhook Server and signature verification.
"""

import time
import hashlib
from wechat_server import check_wechat_signature, build_text_reply_xml, format_wechat_reply, WECHAT_TOKEN
from translator.models import TranslationOutput, Language, TechTerm


def test_wechat_signature_verification():
    token = "my_test_token"
    timestamp = str(int(time.time()))
    nonce = "12345678"
    tmp_list = sorted([token, timestamp, nonce])
    signature = hashlib.sha1("".join(tmp_list).encode("utf-8")).hexdigest()

    assert check_wechat_signature(signature, timestamp, nonce, token=token) is True
    assert check_wechat_signature("invalid_sig", timestamp, nonce, token=token) is False


def test_wechat_xml_reply_builder():
    xml_str = build_text_reply_xml("user_open_id", "bot_id", "Hello WeChat!")
    assert "<ToUserName><![CDATA[user_open_id]]></ToUserName>" in xml_str
    assert "<Content><![CDATA[Hello WeChat!]]></Content>" in xml_str
    assert "<MsgType><![CDATA[text]]></MsgType>" in xml_str


def test_wechat_format_reply():
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
    output = TranslationOutput(query="Привет", detected_lang=Language.RU, direct_match=term)
    formatted = format_wechat_reply(output, "Привет")
    assert "你好" in formatted
    assert "nǐ hǎo" in formatted
    assert "Мэндээ" in formatted
