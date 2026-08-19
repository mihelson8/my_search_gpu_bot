"""
End-to-end tests for the feline triage bot handlers with stubbed Telegram objects.
Проверяется сценарий работы: фото, фотоальбом, видео, инлайн-кнопки, меню.
Сеть не используется: объекты Telegram подменены заглушками.
"""

import io
import shutil
import subprocess
import tempfile
import unittest

import vet_bot
from vetcare.vision import PIL_AVAILABLE

if PIL_AVAILABLE:
    from PIL import Image, ImageDraw


def make_photo_bytes(size=(700, 520), patch_color=(205, 40, 45)):
    image = Image.new("RGB", size, (150, 130, 120))
    draw = ImageDraw.Draw(image)
    for x in range(0, size[0], 3):
        shade = 30 if (x // 3) % 2 else 220
        draw.line([x, 0, x, size[1]], fill=(shade, shade, shade))
    draw.ellipse([200, 150, 500, 400], fill=patch_color)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=92)
    return buffer.getvalue()


def make_video_bytes():
    ffmpeg = shutil.which("ffmpeg")
    with tempfile.TemporaryDirectory() as workdir:
        path = f"{workdir}/sample.mp4"
        subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=320x240:rate=10:duration=4",
                "-pix_fmt",
                "yuv420p",
                path,
                "-y",
            ],
            check=True,
            capture_output=True,
        )
        with open(path, "rb") as handle:
            return handle.read()


class StubFile:
    def __init__(self, data):
        self.data = data

    async def download_as_bytearray(self):
        return bytearray(self.data)


class StubBot:
    def __init__(self, data=b"", log=None):
        self.data = data
        self.log = log if log is not None else []

    async def get_file(self, file_id):
        return StubFile(self.data)

    async def edit_message_text(self, **kwargs):
        self.log.append(("edit_message_text", kwargs.get("text", "")))

    async def set_my_commands(self, commands):
        self.log.append(("set_my_commands", str(len(commands))))


class StubMessage:
    message_id = 101
    chat_id = 55

    def __init__(self, bot, text=None, photo=None, video=None, media_group_id=None):
        self._bot = bot
        self.text = text
        self.photo = photo
        self.video = video
        self.video_note = None
        self.animation = None
        self.document = None
        self.media_group_id = media_group_id

    def get_bot(self):
        return self._bot

    async def reply_text(self, text, **kwargs):
        self._bot.log.append(("reply_text", text))
        return self

    async def edit_text(self, text, **kwargs):
        self._bot.log.append(("edit_text", text))
        return self


class StubPhotoSize:
    file_id = "photo-1"


class StubVideo:
    file_id = "video-1"

    def __init__(self, duration=6, file_size=1024):
        self.duration = duration
        self.file_size = file_size


class StubQuery:
    def __init__(self, bot, data):
        self.data = data
        self.message = StubMessage(bot)
        self._bot = bot

    async def answer(self):
        pass

    async def edit_message_text(self, text, **kwargs):
        self._bot.log.append(("query_text", text))

    async def edit_message_reply_markup(self, **kwargs):
        self._bot.log.append(("query_markup", ""))


class StubUpdate:
    def __init__(self, message=None, callback_query=None):
        self.message = message
        self.callback_query = callback_query


class StubContext:
    def __init__(self, bot):
        self.bot = bot
        self.user_data = {}
        self.args = []


@unittest.skipUnless(PIL_AVAILABLE, "Pillow не установлен")
class TestPhotoFlow(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.log = []
        self.bot = StubBot(make_photo_bytes(), self.log)
        self.context = StubContext(self.bot)

    def texts(self):
        return [text for _, text in self.log]

    async def test_single_photo_creates_suggestions(self):
        message = StubMessage(self.bot, photo=[StubPhotoSize()])
        await vet_bot.photo_handler(StubUpdate(message), self.context)

        session = vet_bot.get_session(self.context)
        self.assertEqual(len(session.media), 1)
        self.assertTrue(session.suggested_signs)
        self.assertTrue(any("Разбор фото" in text for text in self.texts()))

    async def test_album_is_aggregated_into_one_message(self):
        for _ in range(3):
            message = StubMessage(self.bot, photo=[StubPhotoSize()], media_group_id="album-1")
            await vet_bot.photo_handler(StubUpdate(message), self.context)

        session = vet_bot.get_session(self.context)
        self.assertEqual(len(session.media), 3)

        edits = [text for kind, text in self.log if kind == "edit_message_text"]
        self.assertEqual(len(edits), 2)
        self.assertIn("Обработано фото в альбоме", edits[-1])

    async def test_unreadable_photo_is_reported(self):
        broken_bot = StubBot(b"not an image", self.log)
        context = StubContext(broken_bot)
        message = StubMessage(broken_bot, photo=[StubPhotoSize()])
        await vet_bot.photo_handler(StubUpdate(message), context)

        session = vet_bot.get_session(context)
        self.assertEqual(len(session.media), 1)
        self.assertTrue(any("прочитать файл как изображение" in text for text in self.texts()))


@unittest.skipUnless(PIL_AVAILABLE and shutil.which("ffmpeg"), "нужны Pillow и ffmpeg")
class TestVideoFlow(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.video_bytes = make_video_bytes()

    def setUp(self):
        self.log = []
        self.bot = StubBot(self.video_bytes, self.log)
        self.context = StubContext(self.bot)

    async def test_short_video_is_analyzed(self):
        video = StubVideo(duration=4, file_size=len(self.video_bytes))
        await vet_bot.video_handler(StubUpdate(StubMessage(self.bot, video=video)), self.context)

        session = vet_bot.get_session(self.context)
        self.assertEqual(len(session.media), 1)
        analysis = session.media[0]
        self.assertEqual(analysis.kind, "video")
        self.assertGreater(analysis.frames_analyzed, 1)
        self.assertIsNotNone(analysis.motion)

    async def test_long_video_is_rejected_with_guide(self):
        video = StubVideo(duration=300, file_size=len(self.video_bytes))
        await vet_bot.video_handler(StubUpdate(StubMessage(self.bot, video=video)), self.context)

        session = vet_bot.get_session(self.context)
        self.assertEqual(session.media, [])
        texts = [text for _, text in self.log]
        self.assertTrue(any("КАК СНЯТЬ ПОЛЕЗНОЕ ВИДЕО" in text for text in texts))

    async def test_oversized_video_is_rejected(self):
        video = StubVideo(duration=10, file_size=50 * 1024 * 1024)
        await vet_bot.video_handler(StubUpdate(StubMessage(self.bot, video=video)), self.context)
        self.assertEqual(vet_bot.get_session(self.context).media, [])


class TestCallbackFlow(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.log = []
        self.bot = StubBot(b"", self.log)
        self.context = StubContext(self.bot)

    async def press(self, data):
        await vet_bot.callback_handler(
            StubUpdate(callback_query=StubQuery(self.bot, data)), self.context
        )

    async def test_sign_toggle_and_report(self):
        await self.press("zones")
        await self.press("zone:eyes")
        await self.press("sign:eyes:eye_redness")
        await self.press("sign:eyes:eye_discharge")

        session = vet_bot.get_session(self.context)
        self.assertEqual(session.confirmed_signs, {"eye_redness", "eye_discharge"})

        await self.press("report")
        reports = [text for kind, text in self.log if kind == "query_text"]
        self.assertTrue(any("Конъюнктивит" in text for text in reports))

        await self.press("sign:eyes:eye_redness")
        self.assertNotIn("eye_redness", session.confirmed_signs)

    async def test_emergency_sign_triggers_alert(self):
        await self.press("zone:respiratory")
        await self.press("sign:respiratory:breathing_open_mouth")
        texts = [text for _, text in self.log]
        self.assertTrue(any("УГРОЖАЮЩИЙ ПРИЗНАК" in text for text in texts))

    async def test_media_suggestion_buttons(self):
        await self.press("conf:mucosa_yellow")
        session = vet_bot.get_session(self.context)
        self.assertIn("mucosa_yellow", session.confirmed_signs)

        await self.press("no:vomiting")
        self.assertIn("vomiting", session.rejected_signs)

    async def test_report_without_data_prompts_user(self):
        await self.press("report")
        texts = [text for _, text in self.log]
        self.assertTrue(any("Пока нечего оценивать" in text for text in texts))

    async def test_reset_clears_session(self):
        await self.press("conf:vomiting")
        await self.press("reset")
        self.assertTrue(vet_bot.get_session(self.context).is_empty)

    async def test_drug_catalog_navigation(self):
        await self.press("drugs")
        await self.press("dgrp:0")
        await self.press("drug:meloxicam")
        texts = [text for _, text in self.log]
        self.assertTrue(any("Мелоксикам" in text for text in texts))

    async def test_sign_help_card(self):
        await self.press("ask:eye_cornea_cloudy")
        texts = [text for _, text in self.log]
        self.assertTrue(any("Как снять" in text for text in texts))

    async def test_malformed_callback_data_is_ignored(self):
        await self.press("zone:no_such_zone")
        await self.press("dgrp:not_a_number")
        await self.press("drug:no_such_drug")
        self.assertTrue(vet_bot.get_session(self.context).is_empty)


class TestMenuHandlers(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.log = []
        self.bot = StubBot(b"", self.log)
        self.context = StubContext(self.bot)

    async def test_every_menu_button_answers(self):
        for row in vet_bot.MAIN_KEYBOARD:
            for label in row:
                self.log.clear()
                await vet_bot.text_message_handler(
                    StubUpdate(StubMessage(self.bot, text=label)), self.context
                )
                with self.subTest(button=label):
                    self.assertTrue(self.log, f"кнопка {label} не дала ответа")

    async def test_unknown_text_gets_hint(self):
        await vet_bot.text_message_handler(
            StubUpdate(StubMessage(self.bot, text="у кошки что-то с глазом")), self.context
        )
        texts = [text for _, text in self.log]
        self.assertTrue(any("Симптомы по зонам" in text for text in texts))

    async def test_patient_command_saves_data(self):
        self.context.args = ["Барсик", "кот", "5", "4.2"]
        await vet_bot.patient_handler(
            StubUpdate(StubMessage(self.bot, text="/patient")), self.context
        )
        patient = vet_bot.get_session(self.context).patient
        self.assertEqual(patient.name, "Барсик")
        self.assertTrue(patient.is_male)
        self.assertEqual(patient.weight_kg, 4.2)

    async def test_patient_command_without_args_shows_usage(self):
        await vet_bot.patient_handler(
            StubUpdate(StubMessage(self.bot, text="/patient")), self.context
        )
        texts = [text for _, text in self.log]
        self.assertTrue(any("/patient" in text for text in texts))

    async def test_reset_command_clears_album_state(self):
        self.context.user_data["media_group_id"] = "album-1"
        session = vet_bot.get_session(self.context)
        session.confirm("vomiting")
        await vet_bot.reset_handler(StubUpdate(StubMessage(self.bot, text="/reset")), self.context)
        self.assertTrue(session.is_empty)
        self.assertNotIn("media_group_id", self.context.user_data)


if __name__ == "__main__":
    unittest.main()
