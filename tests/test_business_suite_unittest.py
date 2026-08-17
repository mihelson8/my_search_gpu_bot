"""
Simple standalone test runner without external dependencies (unittest).
"""
import unittest
import os
import tempfile
from business_suite_db import BusinessDB

class TestBusinessSuite(unittest.TestCase):
    def setUp(self):
        self.fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(self.fd)
        self.db = BusinessDB(db_path=self.path)

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def test_db_initialization(self):
        tasks = self.db.get_action_tasks()
        templates = self.db.get_templates()
        self.assertEqual(len(tasks), 7)
        self.assertGreaterEqual(len(templates), 4)

    def test_add_and_get_clients(self):
        client_id = self.db.add_client({
            "name": "Иван Тест",
            "phone": "+79991112233",
            "client_type": "individual",
            "year_installed": 2017,
            "cameras_count": 8,
            "system_type": "analog"
        })
        self.assertIsNotNone(client_id)
        client = self.db.get_client_by_id(client_id)
        self.assertEqual(client["name"], "Иван Тест")
        self.assertEqual(client["cameras_count"], 8)

        # Filter test
        ind_clients = self.db.get_clients(client_type="individual")
        self.assertEqual(len(ind_clients), 1)
        biz_clients = self.db.get_clients(client_type="business")
        self.assertEqual(len(biz_clients), 0)

    def test_client_status_update(self):
        client_id = self.db.add_client({
            "name": "ООО Бизнес",
            "client_type": "business"
        })
        self.db.update_client_status(client_id, "upgraded")
        client = self.db.get_client_by_id(client_id)
        self.assertEqual(client["status"], "upgraded")

    def test_7day_tasks_toggle(self):
        tasks = self.db.get_action_tasks()
        first_task = tasks[0]
        self.assertEqual(first_task["is_completed"], 0)

        self.db.toggle_task(first_task["id"])
        updated_tasks = self.db.get_action_tasks()
        self.assertEqual(updated_tasks[0]["is_completed"], 1)

    def test_render_offer_template(self):
        client_id = self.db.add_client({
            "name": "Сергей Викторович",
            "phone": "+79160001122",
            "client_type": "individual",
            "year_installed": 2018,
            "address": "КП Ромашково",
            "cameras_count": 4
        })
        offer_text = self.db.render_template_for_client("offer_individual_night_ai", client_id)
        self.assertIn("Сергей Викторович", offer_text)
        self.assertIn("2018", offer_text)

    def test_import_and_export_csv(self):
        sample_csv = "name,phone,client_type,year_installed,address,cameras_count,system_type,notes\nКлиент 1,+79001111111,individual,2019,Адрес 1,4,analog,Заметка 1\nКлиент 2,+79002222222,business,2020,Адрес 2,12,ip,Заметка 2"
        count = self.db.import_from_csv_text(sample_csv)
        self.assertEqual(count, 2)

        exported = self.db.export_to_csv_text()
        self.assertIn("Клиент 1", exported)
        self.assertIn("Клиент 2", exported)
        self.assertIn("+79001111111", exported)

if __name__ == "__main__":
    unittest.main()
