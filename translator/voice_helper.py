"""
Audio and Voice processing utilities for speech-to-text (STT) and text-to-speech (TTS).
"""

import io
import os
import tempfile
import logging
from typing import Optional, Tuple
from pydub import AudioSegment
import speech_recognition as sr
from gtts import gTTS

from translator.models import Language
from translator.pinyin_helper import detect_language, is_chinese_text

logger = logging.getLogger(__name__)


def generate_tts_audio(text: str, lang: str = "zh") -> Optional[io.BytesIO]:
    """
    Generate MP3 audio bytes using gTTS for pronunciation of words/sentences.
    lang can be 'zh-CN', 'en', 'ru'.
    """
    if not text or not text.strip():
        return None

    lang_map = {
        "zh": "zh-CN",
        "zh-CN": "zh-CN",
        "yue": "yue",
        "cantonese": "yue",
        "en": "en",
        "en_us": "en",
        "en_uk": "en",
        "ru": "ru",
    }
    target_lang = lang_map.get(lang, "zh-CN")

    # Select proper top-level domain (TLD) for English regional accents
    tld = "com"
    if lang in ["en", "en_us"]:
        tld = "com"     # American English accent
    elif lang in ["en_uk", "uk"]:
        tld = "co.uk"   # British English accent

    try:
        tts = gTTS(text=text.strip(), lang=target_lang, tld=tld, slow=False)
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        return audio_buffer
    except Exception as e:
        logger.error(f"TTS generation failed: {e}")
        return None


def recognize_speech_from_ogg(ogg_bytes: bytes) -> Tuple[Optional[str], Optional[Language]]:
    """
    Convert Telegram voice message (OGG/Opus format) to WAV and transcribe speech.
    Tries recognizing Russian, English, and Chinese.
    """
    if not ogg_bytes:
        return None, None

    recognizer = sr.Recognizer()

    try:
        # Convert OGG to WAV using pydub
        ogg_stream = io.BytesIO(ogg_bytes)
        audio = AudioSegment.from_ogg(ogg_stream)
        wav_stream = io.BytesIO()
        audio.export(wav_stream, format="wav")
        wav_stream.seek(0)

        with sr.AudioFile(wav_stream) as source:
            audio_data = recognizer.record(source)

        # Try Google Speech Recognition with multi-language fallback (Russian, English, Mandarin, Cantonese / Baihua, Buryat / Mongolian)
        for lang_code, lang_enum in [("ru-RU", Language.RU), ("en-US", Language.EN), ("zh-CN", Language.ZH), ("zh-HK", Language.ZH), ("yue-Hant-HK", Language.ZH), ("mn-MN", Language.BUA)]:
            try:
                text = recognizer.recognize_google(audio_data, language=lang_code)
                if text and len(text.strip()) > 0:
                    detected = detect_language(text)
                    return text.strip(), detected
            except sr.UnknownValueError:
                continue
            except Exception as e:
                logger.debug(f"Recognition attempt for {lang_code} failed: {e}")
                continue

    except Exception as e:
        logger.error(f"Voice recognition error: {e}", exc_info=True)

    return None, None
