"""
Tests for CCTV & China Business Suite.
"""
import pytest
import os
import tempfile
from business_suite_db import BusinessDB

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = BusinessDB(db_path=path)
    yield db
    if os.path.exists(path):
        os.remove(path)

def test_db_initialization(temp_db):
    tasks = temp_db.get_action_tasks()
    templates = temp_db.get_templates()
    assert len(tasks) == 7
    assert len(templates) >= 4

def test_add_and_get_clients(temp_db):
    client_id = temp_db.add_client({
        "name": "Иван Тест",
        "phone": "+79991112233",
        "client_type": "individual",
        "year_installed": 2017,
        "cameras_count": 8,
        "system_type": "analog"
    })
    assert client_id is not None
    client = temp_db.get_client_by_id(client_id)
    assert client["name"] == "Иван Тест"
    assert client["cameras_count"] == 8

    # Filter test
    ind_clients = temp_db.get_clients(client_type="individual")
    assert len(ind_clients) == 1
    biz_clients = temp_db.get_clients(client_type="business")
    assert len(biz_clients) == 0

def test_client_status_update(temp_db):
    client_id = temp_db.add_client({
        "name": "ООО Бизнес",
        "client_type": "business"
    })
    temp_db.update_client_status(client_id, "upgraded")
    client = temp_db.get_client_by_id(client_id)
    assert client["status"] == "upgraded"

def test_7day_tasks_toggle(temp_db):
    tasks = temp_db.get_action_tasks()
    first_task = tasks[0]
    assert first_task["is_completed"] == 0

    temp_db.toggle_task(first_task["id"])
    updated_tasks = temp_db.get_action_tasks()
    assert updated_tasks[0]["is_completed"] == 1

def test_render_offer_template(temp_db):
    client_id = temp_db.add_client({
        "name": "Сергей Викторович",
        "phone": "+79160001122",
        "client_type": "individual",
        "year_installed": 2018,
        "address": "КП Ромашково",
        "cameras_count": 4
    })
    offer_text = temp_db.render_template_for_client("offer_individual_night_ai", client_id)
    assert "Сергей Викторович" in offer_text
    assert "2018" in offer_text

def test_import_and_export_csv(temp_db):
    sample_csv = "name,phone,client_type,year_installed,address,cameras_count,system_type,notes\nКлиент 1,+79001111111,individual,2019,Адрес 1,4,analog,Заметка 1\nКлиент 2,+79002222222,business,2020,Адрес 2,12,ip,Заметка 2"
    count = temp_db.import_from_csv_text(sample_csv)
    assert count == 2

    exported = temp_db.export_to_csv_text()
    assert "Клиент 1" in exported
    assert "Клиент 2" in exported
    assert "+79001111111" in exported
