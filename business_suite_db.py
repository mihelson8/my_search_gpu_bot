"""
CCTV & China Logistics Business Suite - Database and Core Logic
"""
import sqlite3
import os
import csv
import json
import io
from datetime import datetime
from typing import List, Dict, Any, Optional

def _default_db_path() -> str:
    """Prefer a writable location (AppData on Windows) so USB/ISO disks still work."""
    local_name = "business_suite.db"
    beside_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), local_name)

    # Try next to the program first (convenient for portable use).
    try:
        probe = beside_script + ".write_test"
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
        os.remove(probe)
        return beside_script
    except OSError:
        pass

    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        folder = os.path.join(base, "CCTV_Business_Suite")
    else:
        folder = os.path.join(os.path.expanduser("~"), ".cctv_business_suite")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, local_name)


DEFAULT_DB_PATH = _default_db_path()

class BusinessDB:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        parent = os.path.dirname(os.path.abspath(self.db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Clients table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    phone TEXT,
                    client_type TEXT NOT NULL, -- 'individual' (Физлицо), 'business' (Юрлицо), 'partner' (Партнер/Прораб)
                    year_installed INTEGER,
                    address TEXT,
                    cameras_count INTEGER DEFAULT 0,
                    system_type TEXT, -- 'analog', 'ip', 'hybrid', 'other'
                    equipment_notes TEXT,
                    status TEXT DEFAULT 'new', -- 'new', 'contacted', 'offer_sent', 'upgraded', 'declined', 'on_service'
                    china_interest TEXT DEFAULT 'unknown', -- 'unknown', 'yes', 'no', 'quote_requested'
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 7-Day Action Plan Tasks
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS action_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    day_number INTEGER NOT NULL,
                    day_title TEXT NOT NULL,
                    task_text TEXT NOT NULL,
                    category TEXT NOT NULL, -- 'database', 'upgrade_offer', 'china_kp', 'partners'
                    is_completed INTEGER DEFAULT 0,
                    notes TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Message / Offer Templates
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    target_audience TEXT NOT NULL,
                    content TEXT NOT NULL
                )
            """)

            # China Logistics / CCTV Calculations
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS calculations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER,
                    calc_type TEXT NOT NULL, -- 'cctv_upgrade', 'cctv_new', 'china_cargo'
                    title TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    total_amount REAL DEFAULT 0,
                    margin REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE SET NULL
                )
            """)

            conn.commit()

        self._seed_default_tasks_and_templates()

    def _seed_default_tasks_and_templates(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if templates exist
            cursor.execute("SELECT COUNT(*) FROM templates")
            if cursor.fetchone()[0] == 0:
                default_templates = [
                    (
                        "offer_individual_night_ai",
                        "Модернизация для физлиц (Цветная ночь + AI)",
                        "Физлица (Дома, Дачи, Коттеджи)",
                        "Здравствуйте, {name}! Это ваш мастер по видеонаблюдению. Мы устанавливали вам систему в {year} году.\n\nТехнологии сильно шагнули вперед: сейчас появились камеры с полноцветным ночным видением (в темноте видно как днем) и умным AI-детектором на людей и авто (без ложных тревог от веток и дождя), с мгновенным оповещением на телефон.\n\nСейчас проводим акцию по обновлению старых систем: при модернизации даем скидку 20% на монтаж и берем старое оборудование в зачет (Trade-in).\n\nХотите пришлю пример видео, как камера видит ночью в цвете, и сделаю предварительный расчет?"
                    ),
                    (
                        "offer_business_analytics",
                        "Модернизация для бизнеса (Контроль персонала + Облако)",
                        "Юрлица (Магазины, Склады, Офисы, Автосервисы)",
                        "Добрый день, {name}! Беспокою по поводу системы видеонаблюдения на вашем объекте ({address}), которую монтировали в {year} г.\n\nМногие наши клиенты-предприниматели сейчас обновляют камеры на системы с интеллектуальным контролем: распознавание лиц, контроль кассовой зоны/номеров авто, подсчет посетителей и быстрый удаленный доступ с любого смартфона без сбоев.\n\nТакже предлагаем подключение регламентного ТО (проверка жестких дисков и оптики), чтобы система не подвела в ответственный момент.\n\nКогда вам удобно созвониться на 3 минуты для экспресс-аудита текущего оборудования?"
                    ),
                    (
                        "china_b2b_offer",
                        "Прямые поставки из Китая и Гонконга для юрлиц",
                        "Юрлица и предприниматели",
                        "Здравствуйте, {name}! Помимо систем безопасности, мы с 2016 года наладили прямые поставки оборудования, комплектующих и электроники напрямую с фабрик и рынков Китая (Шэньчжэнь, Гуанчжоу, Иу) и Гонконга.\n\nЧем мы можем быть вам полезны:\n1. Поиск производителей и фабрик под ваш запрос.\n2. Выкуп товаров (1688, Taobao, прямые контракты) без валютных рисков.\n3. Проверка качества на складе в Китае перед отправкой.\n4. Быстрая доставка карго / белая доставка под ключ по выгодному тарифу.\n\nЕсли вы закупаете товары, оборудование, запчасти или расходники — пришлите ссылку, фото или спецификацию, и мы бесплатно рассчитаем себестоимость с доставкой до вашей двери!"
                    ),
                    (
                        "partner_electrician_offer",
                        "Предложение партнерства прорабам и электрикам",
                        "Прорабы, Электрики, Дизайнеры, Монтажники",
                        "Приветствую, {name}! Меня зовут [Ваше Имя], с 2016 года профессионально занимаемся проектированием и монтажом слаботочных систем: видеонаблюдение, СКУД, домофония, бесшовный Wi-Fi, контроль доступа.\n\nПредлагаем взаимовыгодное партнерство:\n- Вы передаете нам контакты клиентов, которым нужна слаботочка / видеонаблюдение.\n- Мы профессионально рассчитываем, монтируем и берем объект на гарантию.\n- Вы получаете от 10% до 15% комиссии с каждого заказа сразу после оплаты клиентом.\n\nЛибо если вам нужны надежные расходники и камеры из Китая по оптовым ценам — можем поставлять напрямую. Давайте обсудим сотрудничество?"
                    ),
                    (
                        "maintenance_contract_offer",
                        "Договор регламентного ТО для юрлиц и коттеджей",
                        "Все клиенты (ТО систем)",
                        "Здравствуйте, {name}! Напоминаем, что средний срок службы жестких дисков в видеорегистраторах составляет 3-4 года. Часто диск выходит из строя незаметно, и когда случается инцидент — записи нет.\n\nМы запустили услугу ежеквартального регламентного обслуживания:\n- Проверка SMART жестких дисков и целостности архива.\n- Чистка оптики, протяжка контактов питания, юстировка камер.\n- Обновление прошивок безопасности от взлома.\n- Выезд мастера в течение 24 часов при любых неполадках.\n\nСтоимость — от 1 500 руб/мес. Готовы закрепить за вашим объектом дежурного инженера."
                    )
                ]
                cursor.executemany(
                    "INSERT INTO templates (code, title, target_audience, content) VALUES (?, ?, ?, ?)",
                    default_templates
                )

            # Check if 7-day action plan tasks exist
            cursor.execute("SELECT COUNT(*) FROM action_tasks")
            if cursor.fetchone()[0] == 0:
                default_tasks = [
                    (1, "День 1: Инвентаризация базы", "Выгрузить и загрузить контакты клиентов в программу. Разделить на Физлица (дома/дачи) и Юрлица (бизнес).", "database"),
                    (2, "День 2: Анализ оборудования", "Проставить в базе примерные годы установки (2016-2020) и типы систем (аналог / старый IP), выделив приоритетных кандидатов на апгрейд.", "database"),
                    (3, "День 3: Запуск рассылки физлицам", "Отправить оффер по модернизации физлицам (цветное ночное видение + AI-оповещения на телефон + Trade-in).", "upgrade_offer"),
                    (4, "День 4: Обзвон теплых откликов и юрлиц", "Обработать ответы физлиц, сделать коммерческие предложения на расчет и позвонить ключевым юрлицам по модернизации и ТО.", "upgrade_offer"),
                    (5, "День 5: КП по Китаю и Гонконгу", "Сделать рассылку по базе юрлиц с предложением поиска и доставки товаров, станков и комплектующих из Китая под ключ.", "china_kp"),
                    (6, "День 6: Поиск и контакт с партнерами", "Найти 10-15 контактов локальных электриков, прорабов и строителей на Авито / в контактах и отправить партнерское предложение с % комиссии.", "partners"),
                    (7, "День 7: Подведение итогов недели", "Собрать воронку: количество отправленных КП, замеры, выставленные счета, заказы на доставку из Китая и запланировать монтажи.", "partners")
                ]
                cursor.executemany(
                    "INSERT INTO action_tasks (day_number, day_title, task_text, category) VALUES (?, ?, ?, ?)",
                    default_tasks
                )

            conn.commit()

    # --- CLIENTS METHODS ---
    def get_clients(self, client_type: Optional[str] = None, status: Optional[str] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            query = "SELECT * FROM clients WHERE 1=1"
            params = []
            if client_type and client_type != 'all':
                query += " AND client_type = ?"
                params.append(client_type)
            if status and status != 'all':
                query += " AND status = ?"
                params.append(status)
            if search:
                query += " AND (name LIKE ? OR phone LIKE ? OR address LIKE ? OR notes LIKE ?)"
                pattern = f"%{search}%"
                params.extend([pattern, pattern, pattern, pattern])
            
            query += " ORDER BY id DESC"
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_client_by_id(self, client_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def add_client(self, data: Dict[str, Any]) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO clients (name, phone, client_type, year_installed, address, cameras_count, system_type, equipment_notes, status, china_interest, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get('name', 'Без имени'),
                data.get('phone', ''),
                data.get('client_type', 'individual'),
                int(data.get('year_installed', 2016)) if data.get('year_installed') else None,
                data.get('address', ''),
                int(data.get('cameras_count', 0)) if data.get('cameras_count') else 0,
                data.get('system_type', 'analog'),
                data.get('equipment_notes', ''),
                data.get('status', 'new'),
                data.get('china_interest', 'unknown'),
                data.get('notes', '')
            ))
            conn.commit()
            return cursor.lastrowid

    def update_client(self, client_id: int, data: Dict[str, Any]) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE clients
                SET name = ?, phone = ?, client_type = ?, year_installed = ?, address = ?,
                    cameras_count = ?, system_type = ?, equipment_notes = ?, status = ?,
                    china_interest = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                data.get('name', ''),
                data.get('phone', ''),
                data.get('client_type', 'individual'),
                int(data.get('year_installed', 2016)) if data.get('year_installed') else None,
                data.get('address', ''),
                int(data.get('cameras_count', 0)) if data.get('cameras_count') else 0,
                data.get('system_type', 'analog'),
                data.get('equipment_notes', ''),
                data.get('status', 'new'),
                data.get('china_interest', 'unknown'),
                data.get('notes', ''),
                client_id
            ))
            conn.commit()
            return cursor.rowcount > 0

    def delete_client(self, client_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM clients WHERE id = ?", (client_id,))
            conn.commit()
            return cursor.rowcount > 0

    def update_client_status(self, client_id: int, status: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE clients SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, client_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_stats(self) -> Dict[str, Any]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM clients")
            total_clients = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM clients WHERE client_type = 'individual'")
            individuals = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM clients WHERE client_type = 'business'")
            businesses = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM clients WHERE client_type = 'partner'")
            partners = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM clients WHERE status = 'upgraded'")
            upgraded = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM clients WHERE status = 'on_service'")
            on_service = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM action_tasks WHERE is_completed = 1")
            completed_tasks = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM action_tasks")
            total_tasks = cursor.fetchone()[0]

            return {
                "total_clients": total_clients,
                "individuals": individuals,
                "businesses": businesses,
                "partners": partners,
                "upgraded": upgraded,
                "on_service": on_service,
                "completed_tasks": completed_tasks,
                "total_tasks": total_tasks,
            }

    # --- CSV / DATA IMPORT & EXPORT ---
    def import_from_csv_text(self, csv_text: str) -> int:
        """Import clients from CSV string."""
        f = io.StringIO(csv_text.strip())
        reader = csv.DictReader(f)
        count = 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for row in reader:
                name = row.get('name') or row.get('Имя') or row.get('ФИО') or 'Клиент'
                phone = row.get('phone') or row.get('Телефон') or ''
                client_type_raw = (row.get('client_type') or row.get('Тип') or 'individual').lower()
                
                if 'юр' in client_type_raw or 'biz' in client_type_raw or 'business' in client_type_raw:
                    client_type = 'business'
                elif 'парт' in client_type_raw or 'прораб' in client_type_raw or 'partner' in client_type_raw:
                    client_type = 'partner'
                else:
                    client_type = 'individual'

                year_raw = row.get('year_installed') or row.get('Год') or '2018'
                try:
                    year = int(str(year_raw).strip())
                except ValueError:
                    year = 2018

                address = row.get('address') or row.get('Адрес') or ''
                cameras_raw = row.get('cameras_count') or row.get('Камер') or '4'
                try:
                    cameras = int(str(cameras_raw).strip())
                except ValueError:
                    cameras = 4

                system_type = row.get('system_type') or row.get('Тип системы') or 'analog'
                notes = row.get('notes') or row.get('Заметки') or ''

                cursor.execute("""
                    INSERT INTO clients (name, phone, client_type, year_installed, address, cameras_count, system_type, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (name, phone, client_type, year, address, cameras, system_type, notes))
                count += 1
            conn.commit()
        return count

    def export_to_csv_text(self, client_type: Optional[str] = None) -> str:
        clients = self.get_clients(client_type=client_type)
        output = io.StringIO()
        fieldnames = ['id', 'name', 'phone', 'client_type', 'year_installed', 'address', 'cameras_count', 'system_type', 'status', 'china_interest', 'notes']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for c in clients:
            writer.writerow({k: c.get(k, '') for k in fieldnames})
        return output.getvalue()

    # --- 7-DAY TASKS METHODS ---
    def get_action_tasks(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM action_tasks ORDER BY day_number ASC, id ASC")
            return [dict(row) for row in cursor.fetchall()]

    def toggle_task(self, task_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE action_tasks SET is_completed = CASE WHEN is_completed = 1 THEN 0 ELSE 1 END, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (task_id,))
            conn.commit()
            return cursor.rowcount > 0

    def add_custom_task(self, day_number: int, day_title: str, task_text: str, category: str = "custom") -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO action_tasks (day_number, day_title, task_text, category)
                VALUES (?, ?, ?, ?)
            """, (day_number, day_title, task_text, category))
            conn.commit()
            return cursor.lastrowid

    # --- TEMPLATES METHODS ---
    def get_templates(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM templates ORDER BY id ASC")
            return [dict(row) for row in cursor.fetchall()]

    def get_template_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM templates WHERE code = ?", (code,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def render_template_for_client(self, template_code: str, client_id: int) -> str:
        client = self.get_client_by_id(client_id)
        template = self.get_template_by_code(template_code)
        if not template:
            return "Шаблон не найден"
        if not client:
            return template['content']

        text = template['content']
        text = text.replace("{name}", client.get('name') or "Уважаемый клиент")
        text = text.replace("{year}", str(client.get('year_installed') or "прошлом"))
        text = text.replace("{address}", client.get('address') or "вашем объекте")
        text = text.replace("{cameras}", str(client.get('cameras_count') or "4"))
        return text

    # --- POPULATE SAMPLE DATA IF EMPTY ---
    def seed_demo_clients(self):
        sample_clients = [
            {"name": "Иванов Сергей (Коттедж)", "phone": "+7 (916) 123-45-67", "client_type": "individual", "year_installed": 2017, "address": "КП Лесные Поляны, дом 42", "cameras_count": 8, "system_type": "analog", "equipment_notes": "Старый 8-канальный аналоговый регистратор AHD 720p, жесткий диск 1ТБ (не менялся с 2017г)", "status": "new", "notes": "Жаловался в прошлый раз, что ночью лица размыты"},
            {"name": "Петров Алексей (Дача)", "phone": "+7 (926) 234-56-78", "client_type": "individual", "year_installed": 2018, "address": "СНТ Родник, уч. 115", "cameras_count": 4, "system_type": "analog", "equipment_notes": "4 камеры 1080p, нет интернета (нужен 4G роутер)", "status": "new", "notes": "Хочет смотреть видео на телефоне в городе"},
            {"name": "Смирнова Елена (Загородный дом)", "phone": "+7 (903) 345-67-89", "client_type": "individual", "year_installed": 2019, "address": "п. Первомайское, ул. Садовая 12", "cameras_count": 6, "system_type": "ip", "equipment_notes": "IP камеры 2Мп, Hikvision. Работают исправно.", "status": "contacted", "notes": "Интересует камера на въезд с распознаванием номеров"},
            {"name": "ООО 'АвтоТехСервис' (Директор Михаил)", "phone": "+7 (915) 456-78-90", "client_type": "business", "year_installed": 2016, "address": "Промзона Южная, бокс 7", "cameras_count": 16, "system_type": "analog", "equipment_notes": "16 камер по всей ремзоне. Провода местами перебиты, картинка рябит.", "status": "new", "china_interest": "yes", "notes": "Также закупают автодиагностику и запчасти из Китая!"},
            {"name": "Складской комплекс 'Логистик-Плюс' (Олег)", "phone": "+7 (925) 567-89-01", "client_type": "business", "year_installed": 2018, "address": "Складской пр-д, стр. 3", "cameras_count": 24, "system_type": "ip", "equipment_notes": "IP видеонаблюдение, 2 регистратора по 32 канала. Нужен регулярный аудит HDD.", "status": "offer_sent", "china_interest": "quote_requested", "notes": "Хотят заказать партию LED-прожекторов и датчиков из Шэньчжэня"},
            {"name": "Сеть кофеен 'Coffee Break' (Анна)", "phone": "+7 (909) 678-90-12", "client_type": "business", "year_installed": 2020, "address": "3 точки в ТЦ города", "cameras_count": 12, "system_type": "ip", "equipment_notes": "Микрофоны над кассами, звук фонит, камеры 2Мп.", "status": "new", "china_interest": "unknown", "notes": "Нужен контроль кассы и четкий звук речи бариста"},
            {"name": "Дмитрий Прораб (Строительство коттеджей)", "phone": "+7 (916) 789-01-23", "client_type": "partner", "year_installed": 2021, "address": "Работает по Новорижскому направлению", "cameras_count": 0, "system_type": "other", "equipment_notes": "Партнер: передает дома на стадии черновой электрики.", "status": "new", "notes": "Предложить 12% с каждого договора на слаботочку"},
            {"name": "Артем Электрик (Частный мастер)", "phone": "+7 (977) 890-12-34", "client_type": "partner", "year_installed": 2022, "address": "Работает по городу и району", "cameras_count": 0, "system_type": "other", "equipment_notes": "Тянет кабель, но не любит настраивать регистраторы и роутеры.", "status": "new", "notes": "Идеально отдавать нам пусконаладку и камеры"}
        ]
        for item in sample_clients:
            self.add_client(item)
