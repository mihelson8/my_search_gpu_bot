"""
Tests for the feline triage Telegram bot: menus, keyboards and input parsing.
Тесты не обращаются к сети: проверяется только сборка меню и разбор ввода.
"""

import unittest

from vet_bot import (
    BOT_COMMANDS,
    MAIN_KEYBOARD,
    MAX_SUGGESTED_BUTTONS,
    MENU_ACTIONS,
    ZONE_ORDER,
    build_drug_groups_keyboard,
    build_drug_list_keyboard,
    build_media_keyboard,
    build_zone_keyboard,
    build_zones_keyboard,
    emergency_alert_html,
    get_session,
    parse_patient_args,
)
from vetcare.engine import CaseSession
from vetcare.knowledge import MEDICATIONS, SIGNS, BodyZone, medication_groups, signs_by_zone
from vetcare.vision import MediaAnalysis, VisualCue


class FakeContext:
    """Минимальная замена ContextTypes.DEFAULT_TYPE для проверки состояния."""

    def __init__(self):
        self.user_data = {}


def all_buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


class TestMenuStructure(unittest.TestCase):
    def test_every_menu_button_has_action(self):
        for row in MAIN_KEYBOARD:
            for label in row:
                with self.subTest(button=label):
                    self.assertIn(label, MENU_ACTIONS)

    def test_all_zones_present_in_menu(self):
        self.assertEqual(set(ZONE_ORDER), set(BodyZone))
        self.assertEqual(len(ZONE_ORDER), len(set(ZONE_ORDER)))

    def test_bot_commands_are_unique_and_described(self):
        commands = [command for command, _ in BOT_COMMANDS]
        self.assertEqual(len(commands), len(set(commands)))
        for command, description in BOT_COMMANDS:
            self.assertTrue(command.islower())
            self.assertTrue(description)


class TestKeyboards(unittest.TestCase):
    def test_zones_keyboard_shows_marked_counters(self):
        session = CaseSession()
        session.confirm("eye_redness")
        session.confirm("eye_discharge")
        labels = [button.text for button in all_buttons(build_zones_keyboard(session))]
        eye_labels = [label for label in labels if "Глаза" in label]
        self.assertEqual(len(eye_labels), 1)
        self.assertIn("(2)", eye_labels[0])

    def test_zone_keyboard_marks_confirmed_signs(self):
        session = CaseSession()
        session.confirm("ear_dark_debris")
        buttons = all_buttons(build_zone_keyboard(BodyZone.EARS, session))
        texts = [button.text for button in buttons]
        confirmed = [text for text in texts if text.startswith("✅")]
        self.assertEqual(len(confirmed), 1)
        self.assertIn("налёт", confirmed[0])
        self.assertTrue(any(text.startswith("⬜") for text in texts))

    def test_zone_keyboard_covers_every_sign_of_the_zone(self):
        session = CaseSession()
        for zone in BodyZone:
            with self.subTest(zone=zone.value):
                markup = build_zone_keyboard(zone, session)
                toggles = [
                    button.callback_data
                    for button in all_buttons(markup)
                    if button.callback_data.startswith("sign:")
                ]
                self.assertEqual(len(toggles), len(signs_by_zone(zone)))

    def test_callback_data_fits_telegram_limit(self):
        session = CaseSession()
        markups = [build_zones_keyboard(session), build_drug_groups_keyboard()]
        markups.extend(build_zone_keyboard(zone, session) for zone in BodyZone)
        markups.extend(
            build_drug_list_keyboard(index) for index in range(len(medication_groups()))
        )
        for markup in markups:
            for button in all_buttons(markup):
                with self.subTest(data=button.callback_data):
                    self.assertLessEqual(len(button.callback_data.encode()), 64)

    def test_media_keyboard_offers_suggested_signs(self):
        session = CaseSession()
        analysis = MediaAnalysis(kind="photo", frames_analyzed=1, quality=None)
        analysis.cues = [
            VisualCue(
                code="redness",
                label="Покраснение",
                confidence=0.6,
                suggested_signs=["eye_redness", "mouth_gum_redness"],
                explanation="тест",
            )
        ]
        session.add_media(analysis)

        buttons = all_buttons(build_media_keyboard(session))
        confirm_data = [
            button.callback_data
            for button in buttons
            if button.callback_data.startswith("conf:")
        ]
        self.assertIn("conf:eye_redness", confirm_data)
        self.assertIn("conf:mouth_gum_redness", confirm_data)
        self.assertTrue(any(button.callback_data == "report" for button in buttons))

    def test_media_keyboard_limits_number_of_suggestions(self):
        session = CaseSession()
        analysis = MediaAnalysis(kind="photo", frames_analyzed=1, quality=None)
        analysis.cues = [
            VisualCue(
                code="many",
                label="Много подсказок",
                confidence=0.5,
                suggested_signs=list(SIGNS.keys()),
                explanation="тест",
            )
        ]
        session.add_media(analysis)
        confirm_buttons = [
            button
            for button in all_buttons(build_media_keyboard(session))
            if button.callback_data.startswith("conf:")
        ]
        self.assertEqual(len(confirm_buttons), MAX_SUGGESTED_BUTTONS)

    def test_drug_keyboards_cover_catalog(self):
        groups = sorted(medication_groups().keys())
        group_buttons = all_buttons(build_drug_groups_keyboard())
        self.assertEqual(len(group_buttons), len(groups))

        listed = set()
        for index in range(len(groups)):
            for button in all_buttons(build_drug_list_keyboard(index)):
                if button.callback_data.startswith("drug:"):
                    listed.add(button.callback_data.split(":", 1)[1])
        self.assertEqual(listed, set(MEDICATIONS.keys()))

    def test_drug_list_keyboard_handles_bad_index(self):
        buttons = all_buttons(build_drug_list_keyboard(999))
        self.assertEqual([button.callback_data for button in buttons], ["drugs"])


class TestPatientParsing(unittest.TestCase):
    def test_full_patient_line(self):
        patient, problems = parse_patient_args(["Барсик", "кот", "5", "4.2"])
        self.assertEqual(patient.name, "Барсик")
        self.assertTrue(patient.is_male)
        self.assertEqual(patient.age_years, 5)
        self.assertEqual(patient.weight_kg, 4.2)
        self.assertEqual(problems, [])

    def test_female_and_comma_decimal(self):
        patient, problems = parse_patient_args(["кошка", "3,5"])
        self.assertFalse(patient.is_male)
        self.assertEqual(patient.age_years, 3.5)
        self.assertEqual(problems, [])

    def test_unrealistic_values_are_rejected(self):
        patient, problems = parse_patient_args(["кот", "150", "99"])
        self.assertIsNone(patient.age_years)
        self.assertIsNone(patient.weight_kg)
        self.assertEqual(len(problems), 2)

    def test_empty_input(self):
        patient, problems = parse_patient_args([])
        self.assertEqual(patient.name, "")
        self.assertIsNone(patient.is_male)
        self.assertEqual(problems, [])


class TestSessionHelpers(unittest.TestCase):
    def test_session_is_created_and_reused(self):
        context = FakeContext()
        session = get_session(context)
        session.confirm("vomiting")
        self.assertIs(get_session(context), session)
        self.assertIn("vomiting", get_session(context).confirmed_signs)

    def test_broken_session_is_replaced(self):
        context = FakeContext()
        context.user_data["session"] = "не сессия"
        self.assertIsInstance(get_session(context), CaseSession)


class TestEmergencyAlert(unittest.TestCase):
    def test_alert_for_emergency_sign(self):
        text = emergency_alert_html("breathing_open_mouth")
        self.assertIsNotNone(text)
        self.assertIn("УГРОЖАЮЩИЙ ПРИЗНАК", text)
        self.assertIn("клинику", text)

    def test_no_alert_for_routine_sign(self):
        self.assertIsNone(emergency_alert_html("obesity"))
        self.assertIsNone(emergency_alert_html("no_such_sign"))


if __name__ == "__main__":
    unittest.main()
