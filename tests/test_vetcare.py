"""
Tests for the feline visual triage knowledge base, engine, vision and media modules.
"""

import io
import shutil
import subprocess
import tempfile
import unittest

from vetcare.engine import (
    EMERGENCY_SIGNS,
    CaseSession,
    DataCompleteness,
    PatientInfo,
    VisualTriageEngine,
    collect_signs_from_media,
)
from vetcare.knowledge import (
    DISEASES,
    MEDICATIONS,
    SIGNS,
    TOXIC_FOR_CATS,
    URGENCY_EMOJI,
    ZONE_LABELS,
    BodyZone,
    Urgency,
    medication_groups,
    signs_by_zone,
)
from vetcare.media import check_video, extract_frames_from_bytes, ffmpeg_path
from vetcare.report import (
    format_assessment_html,
    format_assessment_text,
    format_emergency_html,
    format_first_aid_html,
    format_media_analysis_html,
    format_medication_card_html,
    format_toxic_html,
)
from vetcare.vision import (
    PIL_AVAILABLE,
    MediaAnalysis,
    analyze_frames,
    analyze_image,
    merge_analyses,
    set_classifier,
)

if PIL_AVAILABLE:
    from PIL import Image, ImageDraw, ImageFilter


def make_image_bytes(size=(600, 480), color=(150, 130, 120), patch=None, blur=0):
    """Собирает тестовое изображение с текстурой, чтобы резкость не была нулевой."""
    image = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(image)
    for x in range(0, size[0], 4):
        shade = 40 if (x // 4) % 2 == 0 else 210
        draw.line([x, 0, x, size[1]], fill=(shade, shade, shade), width=1)
    if patch:
        box, patch_color = patch
        draw.ellipse(box, fill=patch_color)
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(blur))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=92)
    return buffer.getvalue()


class TestKnowledgeIntegrity(unittest.TestCase):
    def test_disease_signs_exist(self):
        for code, disease in DISEASES.items():
            with self.subTest(disease=code):
                self.assertTrue(disease.sign_weights, "у болезни нет весов признаков")
                for sign_code in disease.sign_weights:
                    self.assertIn(sign_code, SIGNS)
                for sign_code in disease.key_signs:
                    self.assertIn(sign_code, disease.sign_weights)

    def test_disease_medications_exist(self):
        for code, disease in DISEASES.items():
            with self.subTest(disease=code):
                for med_code in disease.medication_codes:
                    self.assertIn(med_code, MEDICATIONS)

    def test_disease_content_is_filled(self):
        for code, disease in DISEASES.items():
            with self.subTest(disease=code):
                self.assertTrue(disease.diagnostics)
                self.assertTrue(disease.home_care)
                self.assertTrue(disease.description)
                self.assertIsInstance(disease.urgency, Urgency)

    def test_signs_have_labels_and_zones(self):
        for code, sign in SIGNS.items():
            with self.subTest(sign=code):
                self.assertEqual(code, sign.code)
                self.assertIn(sign.zone, ZONE_LABELS)
                self.assertTrue(sign.label)
                self.assertTrue(sign.question.endswith("?"))
                self.assertTrue(sign.media_hint)

    def test_every_zone_has_signs(self):
        for zone in BodyZone:
            with self.subTest(zone=zone.value):
                self.assertTrue(signs_by_zone(zone))

    def test_emergency_signs_are_known(self):
        for code in EMERGENCY_SIGNS:
            self.assertIn(code, SIGNS)

    def test_medications_are_documented(self):
        for code, med in MEDICATIONS.items():
            with self.subTest(med=code):
                self.assertEqual(code, med.code)
                self.assertTrue(med.indications)
                self.assertTrue(med.forms)
                self.assertTrue(med.dose_reference)
                if med.prescription_only:
                    self.assertRegex(
                        med.dose_reference.lower(),
                        r"врач|назнач",
                        "рецептурный препарат должен отсылать к назначению врача",
                    )

    def test_medication_groups_cover_all_drugs(self):
        grouped = sum(len(items) for items in medication_groups().values())
        self.assertEqual(grouped, len(MEDICATIONS))

    def test_urgency_emoji_complete(self):
        for urgency in Urgency:
            self.assertIn(urgency, URGENCY_EMOJI)

    def test_toxic_list_is_filled(self):
        self.assertGreaterEqual(len(TOXIC_FOR_CATS), 5)
        names = " ".join(item.name.lower() for item in TOXIC_FOR_CATS)
        self.assertIn("парацетамол", names)
        self.assertIn("ибупрофен", names)


class TestEngineRanking(unittest.TestCase):
    def setUp(self):
        self.engine = VisualTriageEngine()

    def test_urinary_signs_rank_obstruction_first(self):
        session = CaseSession()
        for code in ("urine_straining", "urine_crying", "urine_blood"):
            session.confirm(code)
        assessment = self.engine.assess(session)
        self.assertIsNotNone(assessment.top)
        self.assertEqual(assessment.top.disease.code, "urinary_obstruction")
        self.assertEqual(assessment.urgency, Urgency.EMERGENCY)

    def test_male_cat_straining_is_emergency(self):
        session = CaseSession(patient=PatientInfo(is_male=True, age_years=4))
        session.confirm("urine_straining")
        assessment = self.engine.assess(session)
        self.assertEqual(assessment.urgency, Urgency.EMERGENCY)

    def test_eye_signs_rank_conjunctivitis(self):
        session = CaseSession()
        session.confirm("eye_redness")
        session.confirm("eye_discharge")
        differentials = self.engine.rank(session)
        codes = [item.disease.code for item in differentials]
        self.assertIn("conjunctivitis_fhv", codes)
        self.assertEqual(codes[0], "conjunctivitis_fhv")

    def test_probabilities_are_bounded(self):
        session = CaseSession()
        for code in ("skin_itching", "skin_black_specks", "skin_miliary_bumps"):
            session.confirm(code)
        differentials = self.engine.rank(session)
        self.assertTrue(differentials)
        total = sum(item.probability for item in differentials)
        self.assertLessEqual(total, 100.5)
        for item in differentials:
            self.assertGreater(item.probability, 0)

    def test_rejected_sign_lowers_probability(self):
        base = CaseSession()
        base.confirm("ear_dark_debris")
        base.confirm("ear_head_shaking")
        before = {item.disease.code: item.probability for item in self.engine.rank(base)}

        base.reject("ear_dark_debris")
        after = {item.disease.code: item.probability for item in self.engine.rank(base)}
        self.assertLess(
            after.get("otodectosis", 0.0),
            before.get("otodectosis", 100.0),
        )

    def test_single_weak_sign_gives_no_confident_list(self):
        session = CaseSession()
        session.confirm("coat_dull")
        self.assertEqual(self.engine.rank(session), [])

    def test_zoonotic_warning_for_ringworm(self):
        session = CaseSession()
        session.confirm("skin_hair_loss_patch")
        session.confirm("skin_scaling_crust")
        assessment = self.engine.assess(session)
        self.assertTrue(assessment.zoonotic_warning)

    def test_red_flags_collected(self):
        session = CaseSession()
        session.confirm("mouth_pale_gums")
        session.confirm("breathing_open_mouth")
        assessment = self.engine.assess(session)
        self.assertEqual(len(assessment.red_flags), 2)
        self.assertEqual(assessment.urgency, Urgency.EMERGENCY)

    def test_senior_cat_escalates_soon_to_urgent(self):
        session = CaseSession(patient=PatientInfo(age_years=13))
        session.confirm("urine_increased")
        session.confirm("weight_loss")
        assessment = self.engine.assess(session)
        self.assertEqual(assessment.urgency, Urgency.URGENT)

    def test_medication_codes_are_resolvable(self):
        session = CaseSession()
        session.confirm("eye_redness")
        session.confirm("eye_discharge")
        assessment = self.engine.assess(session)
        self.assertTrue(assessment.medication_codes)
        for code in assessment.medication_codes:
            self.assertIn(code, MEDICATIONS)

    def test_empty_session_still_asks_questions(self):
        session = CaseSession()
        assessment = self.engine.assess(session)
        self.assertEqual(assessment.differentials, [])
        self.assertTrue(assessment.next_questions)
        self.assertEqual(assessment.completeness, DataCompleteness.LOW)

    def test_next_questions_skip_answered_signs(self):
        session = CaseSession()
        session.confirm("eye_redness")
        session.reject("eye_squint")
        questions = self.engine.next_questions(session)
        codes = {sign.code for sign in questions}
        self.assertNotIn("eye_redness", codes)
        self.assertNotIn("eye_squint", codes)


class TestSessionState(unittest.TestCase):
    def test_toggle_and_reset(self):
        session = CaseSession()
        self.assertTrue(session.toggle("eye_redness"))
        self.assertIn("eye_redness", session.confirmed_signs)
        self.assertFalse(session.toggle("eye_redness"))
        self.assertNotIn("eye_redness", session.confirmed_signs)

        session.confirm("vomiting")
        session.reject("diarrhea")
        self.assertFalse(session.is_empty)
        session.reset()
        self.assertTrue(session.is_empty)
        self.assertFalse(session.confirmed_signs)
        self.assertFalse(session.rejected_signs)

    def test_unknown_sign_is_ignored(self):
        session = CaseSession()
        self.assertFalse(session.confirm("no_such_sign"))
        self.assertFalse(session.reject("no_such_sign"))
        self.assertFalse(session.confirmed_signs)

    def test_confirm_clears_rejection(self):
        session = CaseSession()
        session.reject("vomiting")
        session.confirm("vomiting")
        self.assertIn("vomiting", session.confirmed_signs)
        self.assertNotIn("vomiting", session.rejected_signs)

    def test_media_suggestions_feed_session(self):
        analysis = MediaAnalysis(kind="photo", frames_analyzed=1, quality=None)
        analysis.cues = analyze_stub_cues()
        session = CaseSession()
        session.add_media(analysis)
        self.assertIn("eye_redness", session.suggested_signs)
        self.assertIn("eye_redness", collect_signs_from_media(session.media))
        self.assertGreater(session.media_confidence_boost.get("eye_redness", 0), 0)

        session.confirm("eye_redness")
        self.assertNotIn("eye_redness", session.suggested_signs)


def analyze_stub_cues():
    from vetcare.vision import VisualCue

    return [
        VisualCue(
            code="redness",
            label="Покраснение",
            confidence=0.5,
            suggested_signs=["eye_redness"],
            explanation="тест",
        )
    ]


@unittest.skipUnless(PIL_AVAILABLE, "Pillow не установлен")
class TestVision(unittest.TestCase):
    def test_red_patch_produces_redness_cue(self):
        data = make_image_bytes(patch=((150, 120, 450, 360), (205, 35, 40)))
        analysis = analyze_image(data)
        codes = {cue.code for cue in analysis.cues}
        self.assertIn("redness", codes)
        self.assertIn("eye_redness", analysis.suggested_signs)

    def test_quality_flags_small_and_dark_image(self):
        data = make_image_bytes(size=(120, 90), color=(8, 8, 8))
        analysis = analyze_image(data)
        self.assertIsNotNone(analysis.quality)
        self.assertFalse(analysis.quality.is_usable)
        problems = " ".join(analysis.quality.problems)
        self.assertIn("разрешение", problems)
        self.assertIn("тёмный", problems)

    def test_blurred_image_is_less_sharp(self):
        sharp = analyze_image(make_image_bytes())
        blurred = analyze_image(make_image_bytes(blur=6))
        self.assertGreater(sharp.quality.sharpness, blurred.quality.sharpness)
        self.assertTrue(sharp.quality.is_usable)

    def test_broken_bytes_are_handled(self):
        analysis = analyze_image(b"definitely not an image")
        self.assertIsNone(analysis.quality)
        self.assertEqual(analysis.frames_analyzed, 0)
        self.assertTrue(analysis.notes)

    def test_analyze_frames_without_frames(self):
        analysis = analyze_frames([])
        self.assertEqual(analysis.frames_analyzed, 0)
        self.assertTrue(analysis.notes)

    def test_analyze_frames_aggregates_cues_and_motion(self):
        frames = [
            make_image_bytes(patch=((150 + shift, 120, 450 + shift, 360), (205, 35, 40)))
            for shift in (0, 20, 40, 60, 80, 100)
        ]
        analysis = analyze_frames(frames)
        self.assertEqual(analysis.frames_analyzed, len(frames))
        self.assertIsNotNone(analysis.motion)
        self.assertEqual(analysis.motion.frames, len(frames))
        self.assertIn("redness", {cue.code for cue in analysis.cues})

    def test_repeated_cue_beats_single_frame_cue(self):
        red = make_image_bytes(patch=((150, 120, 450, 360), (205, 35, 40)))
        plain_frame = make_image_bytes()
        stable = analyze_frames([red, red, red, red])
        noisy = analyze_frames([red, plain_frame, plain_frame, plain_frame])

        def redness(analysis):
            for cue in analysis.cues:
                if cue.code == "redness":
                    return cue.confidence
            return 0.0

        self.assertGreater(redness(stable), redness(noisy))

    def test_merge_analyses_of_album(self):
        first = analyze_image(make_image_bytes(patch=((150, 120, 450, 360), (205, 35, 40))))
        second = analyze_image(make_image_bytes())
        merged = merge_analyses([first, second])
        self.assertEqual(merged.kind, "photo")
        self.assertGreaterEqual(merged.frames_analyzed, 2)
        self.assertIn("redness", {cue.code for cue in merged.cues})

    def test_external_classifier_hook(self):
        class FakeClassifier:
            def predict(self, image_bytes):
                return [("eye_cornea_cloudy", 0.81), ("skin_itching", 0.1)]

        set_classifier(FakeClassifier())
        try:
            analysis = analyze_image(make_image_bytes())
        finally:
            set_classifier(None)

        codes = {cue.code for cue in analysis.cues}
        self.assertIn("model_eye_cornea_cloudy", codes)
        self.assertIn("eye_cornea_cloudy", analysis.suggested_signs)
        self.assertNotIn("model_skin_itching", codes)

    def test_failing_classifier_does_not_break_analysis(self):
        class BrokenClassifier:
            def predict(self, image_bytes):
                raise RuntimeError("model is not loaded")

        set_classifier(BrokenClassifier())
        try:
            analysis = analyze_image(make_image_bytes())
        finally:
            set_classifier(None)
        self.assertIsNotNone(analysis.quality)


class TestMedia(unittest.TestCase):
    def test_check_video_limits(self):
        self.assertTrue(check_video(20, 5 * 1024 * 1024).accepted)

        too_long = check_video(120, 1024)
        self.assertFalse(too_long.accepted)
        self.assertIn("длительность", too_long.message)

        too_big = check_video(10, 40 * 1024 * 1024)
        self.assertFalse(too_big.accepted)
        self.assertIn("МБ", too_big.message)

    def test_check_video_without_metadata(self):
        self.assertTrue(check_video(None, None).accepted)

    def test_extract_frames_from_garbage(self):
        self.assertEqual(extract_frames_from_bytes(b"not a video"), [])

    @unittest.skipUnless(ffmpeg_path() and PIL_AVAILABLE, "нужны ffmpeg и Pillow")
    def test_extract_frames_from_real_video(self):
        with tempfile.TemporaryDirectory() as workdir:
            path = f"{workdir}/sample.mp4"
            subprocess.run(
                [
                    shutil.which("ffmpeg"),
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
                data = handle.read()

        frames = extract_frames_from_bytes(data, max_frames=6)
        self.assertTrue(frames)
        self.assertLessEqual(len(frames), 6)

        analysis = analyze_frames(frames, kind="video")
        self.assertGreater(analysis.frames_analyzed, 0)
        self.assertIsNotNone(analysis.motion)


class TestReportFormatting(unittest.TestCase):
    def setUp(self):
        self.engine = VisualTriageEngine()

    def test_assessment_html_contains_key_blocks(self):
        session = CaseSession(patient=PatientInfo(name="Барсик", is_male=True, age_years=5))
        session.confirm("urine_straining")
        session.confirm("urine_blood")
        text = format_assessment_html(self.engine.assess(session), session)

        self.assertIn("ПРЕДВАРИТЕЛЬНАЯ ОЦЕНКА", text)
        self.assertIn("Барсик", text)
        self.assertIn("Срочность", text)
        self.assertIn("Закупорка уретры", text)
        self.assertIn("не ставит диагноз", text)
        self.assertIn("круглосуточную клинику", text)

    def test_assessment_html_without_signs(self):
        text = format_assessment_html(self.engine.assess(CaseSession()))
        self.assertIn("Признаки пока не отмечены", text)
        self.assertIn("не ставит диагноз", text)

    def test_assessment_text_for_console(self):
        session = CaseSession()
        session.confirm("skin_hair_loss_patch")
        session.confirm("skin_scaling_crust")
        text = format_assessment_text(self.engine.assess(session))
        self.assertIn("Вероятные состояния", text)
        self.assertIn("Дерматофития", text)
        self.assertNotIn("<b>", text)

    def test_medication_card_has_dose_and_warning(self):
        text = format_medication_card_html(MEDICATIONS["meloxicam"])
        self.assertIn("Мелоксикам", text)
        self.assertIn("Дозировка (справочно)", text)
        self.assertIn("Противопоказания", text)
        self.assertIn("назначению ветеринарного врача", text)

    def test_static_sections(self):
        self.assertIn("ЭКСТРЕННЫЕ ПРИЗНАКИ", format_emergency_html())
        self.assertIn("ПЕРВАЯ ПОМОЩЬ", format_first_aid_html())
        toxic = format_toxic_html()
        self.assertIn("Парацетамол", toxic)
        self.assertIn("Перметрин", toxic)

    @unittest.skipUnless(PIL_AVAILABLE, "Pillow не установлен")
    def test_media_analysis_html(self):
        analysis = analyze_image(make_image_bytes(patch=((150, 120, 450, 360), (205, 35, 40))))
        text = format_media_analysis_html(analysis)
        self.assertIn("Разбор фото", text)
        self.assertIn("уверенность", text)
        self.assertIn("не являются диагнозом", text)


if __name__ == "__main__":
    unittest.main()
