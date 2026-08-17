"""
Tests for Voice and Audio TTS/STT helpers.
"""

from translator.voice_helper import generate_tts_audio


def test_generate_tts_audio_chinese():
    audio_stream = generate_tts_audio("人工智能", lang="zh")
    assert audio_stream is not None
    bytes_data = audio_stream.read()
    assert len(bytes_data) > 0


def test_generate_tts_audio_cantonese_baihua():
    audio_stream = generate_tts_audio("人工智能", lang="yue")
    assert audio_stream is not None
    bytes_data = audio_stream.read()
    assert len(bytes_data) > 0


def test_generate_tts_audio_english():
    audio_stream = generate_tts_audio("Deep Learning", lang="en")
    assert audio_stream is not None
    bytes_data = audio_stream.read()
    assert len(bytes_data) > 0


def test_generate_tts_audio_empty():
    assert generate_tts_audio("") is None
    assert generate_tts_audio("   ") is None
