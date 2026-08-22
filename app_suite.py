"""
Web & Desktop Application for CCTV & China Business Suite
Runs locally and can be accessed via browser or packaged as a desktop window.
"""
import os
import json
import urllib.parse
from http.server import SimpleHTTPRequestHandler, HTTPServer
import threading
import webbrowser
from typing import Any
from business_suite_db import BusinessDB, DEFAULT_DB_PATH

try:
    db = BusinessDB()
    # If DB is completely empty of clients, seed demo data for an immediate great experience
    if len(db.get_clients()) == 0:
        db.seed_demo_clients()
except Exception as exc:
    print("============================================================")
    print("ОШИБКА при открытии базы данных")
    print(exc)
    print()
    print("Скопируйте папку программы на диск C: (например C:\\бизнес)")
    print("и запустите START_APP_WINDOWS.bat оттуда.")
    print("Диск G: часто бывает только для чтения (флешка Windows).")
    print("============================================================")
    raise SystemExit(1) from exc

HTML_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CCTV & China Cargo Suite - Пульт управления бизнесом</title>
    <link rel="icon" type="image/png" href="/app_icon.png">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #2563eb;
            --primary-hover: #1d4ed8;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --dark-bg: #0f172a;
            --card-bg: #1e293b;
            --sidebar-bg: #111827;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --border: #334155;
            --accent: #38bdf8;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }

        body {
            background-color: var(--dark-bg);
            color: var(--text-main);
            display: flex;
            height: 100vh;
            overflow: hidden;
        }

        /* Sidebar */
        aside {
            width: 260px;
            background-color: var(--sidebar-bg);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            padding: 20px 15px;
            flex-shrink: 0;
        }

        .logo-area {
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 20px;
        }

        .logo-title {
            font-size: 18px;
            font-weight: 700;
            color: #fff;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .logo-sub {
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 4px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        nav {
            display: flex;
            flex-direction: column;
            gap: 6px;
            flex-grow: 1;
        }

        .nav-btn {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 14px;
            border-radius: 8px;
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            text-align: left;
            width: 100%;
        }

        .nav-btn:hover {
            background-color: rgba(255, 255, 255, 0.05);
            color: var(--text-main);
        }

        .nav-btn.active {
            background-color: var(--primary);
            color: #fff;
            font-weight: 600;
        }

        .stats-badge {
            margin-left: auto;
            background: rgba(255, 255, 255, 0.15);
            padding: 2px 7px;
            border-radius: 10px;
            font-size: 11px;
        }

        /* Main Content */
        main {
            flex-grow: 1;
            display: flex;
            flex-direction: column;
            overflow-y: auto;
            padding: 24px 30px;
            background-color: var(--dark-bg);
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
        }

        .header-title h1 {
            font-size: 24px;
            font-weight: 700;
        }

        .header-title p {
            color: var(--text-muted);
            font-size: 13px;
            margin-top: 4px;
        }

        .stats-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }

        .stat-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            padding: 18px;
            border-radius: 12px;
        }

        .stat-label {
            font-size: 12px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .stat-val {
            font-size: 26px;
            font-weight: 700;
            margin-top: 6px;
            color: #fff;
        }

        .tab-content {
            display: none;
        }

        .tab-content.active {
            display: block;
        }

        /* Tables & Lists */
        .card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }

        .card-title {
            font-size: 16px;
            font-weight: 600;
        }

        .btn {
            background-color: var(--primary);
            color: #fff;
            border: none;
            padding: 9px 16px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }

        .btn:hover {
            background-color: var(--primary-hover);
        }

        .btn-secondary {
            background: #334155;
        }
        .btn-secondary:hover {
            background: #475569;
        }

        .btn-success {
            background: var(--success);
        }
        .btn-success:hover {
            background: #059669;
        }

        .btn-sm {
            padding: 5px 10px;
            font-size: 12px;
        }

        /* Filter Controls */
        .filter-bar {
            display: flex;
            gap: 12px;
            margin-bottom: 16px;
            flex-wrap: wrap;
        }

        input, select, textarea {
            background: #0f172a;
            border: 1px solid var(--border);
            color: #fff;
            padding: 9px 12px;
            border-radius: 6px;
            font-size: 13px;
            outline: none;
        }

        input:focus, select:focus, textarea:focus {
            border-color: var(--accent);
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }

        th {
            text-align: left;
            padding: 12px 14px;
            background: #111827;
            color: var(--text-muted);
            border-bottom: 1px solid var(--border);
            font-weight: 600;
        }

        td {
            padding: 14px;
            border-bottom: 1px solid rgba(51, 65, 85, 0.5);
            vertical-align: middle;
        }

        tr:hover td {
            background: rgba(255, 255, 255, 0.02);
        }

        .badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }

        .badge-ind { background: rgba(56, 189, 248, 0.15); color: #38bdf8; }
        .badge-biz { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
        .badge-part { background: rgba(168, 85, 247, 0.15); color: #c084fc; }

        .badge-status-new { background: #334155; color: #94a3b8; }
        .badge-status-contacted { background: #1e3a8a; color: #93c5fd; }
        .badge-status-offer_sent { background: #78350f; color: #fde68a; }
        .badge-status-upgraded { background: #064e3b; color: #6ee7b7; }
        .badge-status-on_service { background: #3b0764; color: #d8b4fe; }

        /* 7-Day Plan Item */
        .plan-item {
            background: #111827;
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 12px;
            display: flex;
            align-items: flex-start;
            gap: 16px;
            transition: all 0.2s;
        }

        .plan-item.completed {
            border-color: var(--success);
            background: rgba(16, 185, 129, 0.05);
            opacity: 0.85;
        }

        .plan-checkbox {
            width: 20px;
            height: 20px;
            accent-color: var(--success);
            cursor: pointer;
            margin-top: 3px;
        }

        .plan-body {
            flex-grow: 1;
        }

        .plan-day-tag {
            font-size: 12px;
            font-weight: 700;
            color: var(--accent);
            text-transform: uppercase;
            margin-bottom: 4px;
        }

        .plan-title {
            font-size: 15px;
            font-weight: 600;
            margin-bottom: 6px;
        }

        .plan-desc {
            font-size: 13px;
            color: var(--text-muted);
            line-height: 1.5;
        }

        /* Template card */
        .template-card {
            background: #111827;
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 18px;
            margin-bottom: 16px;
        }

        .template-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }

        .template-title {
            font-size: 15px;
            font-weight: 600;
            color: #fff;
        }

        .template-text-box {
            background: #090d16;
            border: 1px solid #1e293b;
            padding: 14px;
            border-radius: 8px;
            font-size: 13px;
            color: #e2e8f0;
            white-space: pre-wrap;
            line-height: 1.5;
            font-family: inherit;
            margin-bottom: 12px;
        }

        /* Modal */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.7);
            z-index: 1000;
            align-items: center;
            justify-content: center;
        }

        .modal-overlay.active {
            display: flex;
        }

        .modal {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            width: 600px;
            max-width: 90vw;
            max-height: 90vh;
            overflow-y: auto;
            padding: 24px;
        }

        .modal-title {
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 16px;
        }

        .form-group {
            margin-bottom: 14px;
        }

        .form-group label {
            display: block;
            font-size: 12px;
            color: var(--text-muted);
            margin-bottom: 6px;
            font-weight: 500;
        }

        .form-group input, .form-group select, .form-group textarea {
            width: 100%;
        }

        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }

        .modal-actions {
            display: flex;
            justify-content: flex-end;
            gap: 10px;
            margin-top: 20px;
        }

        /* Toast notification */
        #toast {
            visibility: hidden;
            min-width: 250px;
            background-color: var(--success);
            color: #fff;
            text-align: center;
            border-radius: 8px;
            padding: 12px 20px;
            position: fixed;
            z-index: 2000;
            right: 30px;
            bottom: 30px;
            font-size: 14px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.4);
            font-weight: 500;
        }

        #toast.show {
            visibility: visible;
            animation: fadein 0.3s, fadeout 0.5s 2.5s;
        }

        @keyframes fadein { from { bottom: 0; opacity: 0; } to { bottom: 30px; opacity: 1; } }
        @keyframes fadeout { from { bottom: 30px; opacity: 1; } to { bottom: 0; opacity: 0; } }

        /* Quick Calculator UI */
        .calc-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }

        .calc-box {
            background: #111827;
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 18px;
        }

        .calc-result-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid var(--border);
            font-size: 13px;
        }

        .calc-result-total {
            display: flex;
            justify-content: space-between;
            padding: 12px 0 0 0;
            font-size: 16px;
            font-weight: 700;
            color: var(--accent);
        }
    </style>
</head>
<body>

    <!-- Sidebar Navigation -->
    <aside>
        <div class="logo-area">
            <div class="logo-title">
                📹 🇨🇳 Business Suite
            </div>
            <div class="logo-sub">Видеонаблюдение & Китай / Гонконг</div>
        </div>

        <nav>
            <button class="nav-btn active" onclick="switchTab('tab-clients')">
                👥 База клиентов
                <span class="stats-badge" id="badge-total-clients">0</span>
            </button>
            <button class="nav-btn" onclick="switchTab('tab-7days')">
                📅 План на 7 дней
                <span class="stats-badge" id="badge-tasks">0/7</span>
            </button>
            <button class="nav-btn" onclick="switchTab('tab-offers')">
                💬 Шаблоны офферов & КП
            </button>
            <button class="nav-btn" onclick="switchTab('tab-calculators')">
                🧮 Калькуляторы (Апгрейд / Карго)
            </button>
            <button class="nav-btn" onclick="switchTab('tab-import')">
                📥 Импорт & Экспорт (Excel/CSV)
            </button>
        </nav>

        <div style="font-size: 11px; color: var(--text-muted); text-align: center; padding-top: 15px; border-top: 1px solid var(--border);">
            Работает локально на вашем ПК (Windows)
        </div>
    </aside>

    <!-- Main Content Area -->
    <main>
        <!-- Top Stats Row -->
        <div class="stats-row">
            <div class="stat-card">
                <div class="stat-label">Всего клиентов в базе</div>
                <div class="stat-val" id="stat-total">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Физлица (Коттеджи / Дачи)</div>
                <div class="stat-val" style="color: #38bdf8;" id="stat-ind">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Юрлица (Бизнес / Склады)</div>
                <div class="stat-val" style="color: #f59e0b;" id="stat-biz">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Партнеры (Прорабы / Электрики)</div>
                <div class="stat-val" style="color: #c084fc;" id="stat-part">0</div>
            </div>
        </div>

        <!-- TAB 1: CLIENTS DATABASE -->
        <div id="tab-clients" class="tab-content active">
            <div class="card">
                <div class="card-header">
                    <div class="card-title">Клиенты и объекты (с 2016 года)</div>
                    <div style="display: flex; gap: 8px;">
                        <button class="btn btn-success btn-sm" onclick="openAddClientModal()">+ Добавить клиента</button>
                    </div>
                </div>

                <div class="filter-bar">
                    <input type="text" id="search-input" placeholder="🔍 Поиск по имени, телефону, адресу..." style="width: 280px;" oninput="loadClients()">
                    <select id="filter-type" onchange="loadClients()">
                        <option value="all">Все типы клиентов</option>
                        <option value="individual">🏡 Физлица (Дома/Дачи)</option>
                        <option value="business">🏢 Юрлица (Бизнес)</option>
                        <option value="partner">🤝 Партнеры (Прорабы/Электрики)</option>
                    </select>
                    <select id="filter-status" onchange="loadClients()">
                        <option value="all">Все статусы</option>
                        <option value="new">Новый / Не обработан</option>
                        <option value="contacted">Установлен контакт</option>
                        <option value="offer_sent">Оффер / КП отправлен</option>
                        <option value="upgraded">✅ Модернизирован</option>
                        <option value="on_service">🛡 На обслуживании (ТО)</option>
                    </select>
                </div>

                <div style="overflow-x: auto;">
                    <table>
                        <thead>
                            <tr>
                                <th>Имя / Объект</th>
                                <th>Телефон</th>
                                <th>Тип</th>
                                <th>Год монтажа</th>
                                <th>Камер / Система</th>
                                <th>Статус</th>
                                <th>Интерес к Китаю</th>
                                <th>Действия</th>
                            </tr>
                        </thead>
                        <tbody id="clients-table-body">
                            <!-- Populated dynamically via JS -->
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- TAB 2: 7-DAY ACTION PLAN -->
        <div id="tab-7days" class="tab-content">
            <div class="card">
                <div class="card-header">
                    <div>
                        <div class="card-title">🚀 Пошаговый 7-дневный план масштабирования</div>
                        <p style="color: var(--text-muted); font-size: 13px; margin-top: 4px;">Отмечайте галочками выполненные шаги. Программа автоматически пересчитывает прогресс.</p>
                    </div>
                    <button class="btn btn-secondary btn-sm" onclick="loadTasks()">🔄 Обновить</button>
                </div>

                <div id="action-tasks-container">
                    <!-- Action tasks populated by JS -->
                </div>
            </div>
        </div>

        <!-- TAB 3: OFFER TEMPLATES & SCRIPTS -->
        <div id="tab-offers" class="tab-content">
            <div class="card">
                <div class="card-header">
                    <div>
                        <div class="card-title">💬 Готовые коммерческие предложения и скрипты рассылок</div>
                        <p style="color: var(--text-muted); font-size: 13px; margin-top: 4px;">Протестированные тексты сообщений для WhatsApp, Telegram и звонков</p>
                    </div>
                </div>

                <div id="templates-container">
                    <!-- Templates populated by JS -->
                </div>
            </div>
        </div>

        <!-- TAB 4: CALCULATORS (UPGRADE & CHINA CARGO) -->
        <div id="tab-calculators" class="tab-content">
            <div class="card">
                <div class="card-title" style="margin-bottom: 16px;">🧮 Экспресс-калькуляторы для расчетов клиентам</div>
                
                <div class="calc-grid">
                    <!-- CCTV Upgrade Calculator -->
                    <div class="calc-box">
                        <h3 style="font-size: 15px; margin-bottom: 12px; color: #38bdf8;">📹 Расчет апгрейда видеонаблюдения</h3>
                        <div class="form-group">
                            <label>Количество камер под замену:</label>
                            <input type="number" id="calc-cctv-cams" value="4" oninput="recalcCctv()">
                        </div>
                        <div class="form-group">
                            <label>Стоимость 1 камеры клиенту (руб):</label>
                            <input type="number" id="calc-cctv-cam-price" value="4500" oninput="recalcCctv()">
                        </div>
                        <div class="form-group">
                            <label>Замена видеорегистратора + HDD (руб):</label>
                            <input type="number" id="calc-cctv-nvr-price" value="16000" oninput="recalcCctv()">
                        </div>
                        <div class="form-group">
                            <label>Монтаж / юстировка (руб за точку):</label>
                            <input type="number" id="calc-cctv-work" value="1800" oninput="recalcCctv()">
                        </div>
                        <div class="form-group">
                            <label>Скидка по акции / Trade-in (%):</label>
                            <input type="number" id="calc-cctv-discount" value="15" oninput="recalcCctv()">
                        </div>

                        <div style="margin-top: 14px; background: #090d16; padding: 12px; border-radius: 8px;">
                            <div class="calc-result-row">
                                <span>Оборудование:</span>
                                <span id="res-cctv-equip">0 руб.</span>
                            </div>
                            <div class="calc-result-row">
                                <span>Работы и настройка:</span>
                                <span id="res-cctv-work">0 руб.</span>
                            </div>
                            <div class="calc-result-row">
                                <span>Скидка Trade-in:</span>
                                <span style="color: #ef4444;" id="res-cctv-discount">-0 руб.</span>
                            </div>
                            <div class="calc-result-total">
                                <span>ИТОГО КЛИЕНТУ:</span>
                                <span id="res-cctv-total">0 руб.</span>
                            </div>
                        </div>
                    </div>

                    <!-- China Cargo Logistics Calculator -->
                    <div class="calc-box">
                        <h3 style="font-size: 15px; margin-bottom: 12px; color: #f59e0b;">🇨🇳 Расчет доставки груза из Китая / Гонконга</h3>
                        <div class="form-group">
                            <label>Стоимость товара в Китае (¥ Юани):</label>
                            <input type="number" id="calc-china-yuan" value="10000" oninput="recalcChina()">
                        </div>
                        <div class="form-group">
                            <label>Курс Юаня к Рублю (₽):</label>
                            <input type="number" id="calc-china-rate" value="13.8" step="0.1" oninput="recalcChina()">
                        </div>
                        <div class="form-group">
                            <label>Вес груза (кг):</label>
                            <input type="number" id="calc-china-weight" value="45" oninput="recalcChina()">
                        </div>
                        <div class="form-group">
                            <label>Тариф доставки за кг ($ USD):</label>
                            <input type="number" id="calc-china-tariff-usd" value="4.5" step="0.1" oninput="recalcChina()">
                        </div>
                        <div class="form-group">
                            <label>Курс USD к Рублю (₽):</label>
                            <input type="number" id="calc-usd-rate" value="95.0" oninput="recalcChina()">
                        </div>
                        <div class="form-group">
                            <label>Ваша комиссия за выкуп и поиск (%):</label>
                            <input type="number" id="calc-china-margin" value="10" oninput="recalcChina()">
                        </div>

                        <div style="margin-top: 14px; background: #090d16; padding: 12px; border-radius: 8px;">
                            <div class="calc-result-row">
                                <span>Выкуп товара:</span>
                                <span id="res-china-goods">0 руб.</span>
                            </div>
                            <div class="calc-result-row">
                                <span>Доставка Карго:</span>
                                <span id="res-china-shipping">0 руб.</span>
                            </div>
                            <div class="calc-result-row">
                                <span>Ваша комиссия / прибыль:</span>
                                <span style="color: #10b981;" id="res-china-commission">0 руб.</span>
                            </div>
                            <div class="calc-result-total">
                                <span>ИТОГО КЛИЕНТУ В РФ:</span>
                                <span id="res-china-total">0 руб.</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB 5: IMPORT / EXPORT -->
        <div id="tab-import" class="tab-content">
            <div class="card">
                <div class="card-title" style="margin-bottom: 12px;">📥 Быстрый импорт базы клиентов (Excel / CSV / Текст)</div>
                <p style="color: var(--text-muted); font-size: 13px; margin-bottom: 16px;">
                    Вы можете вставить строки в формате CSV (разделитель запятая) или скопировать прямо из Excel.
                </p>

                <div class="form-group">
                    <label>Вставьте текст CSV (Имя, Телефон, Тип, Год, Адрес, Камер, Система, Заметки):</label>
                    <textarea id="import-csv-area" rows="8" placeholder="name,phone,client_type,year_installed,address,cameras_count,system_type,notes
Иван Смирнов (Коттедж),+79161234567,individual,2017,КП Дубки,8,analog,Старый регистратор
ООО Альфа Склад,+79261112233,business,2018,Промзона 5,16,ip,Интересуются выкупом из Китая"></textarea>
                </div>

                <div style="display: flex; gap: 10px;">
                    <button class="btn btn-success" onclick="executeImport()">🚀 Импортировать клиентов</button>
                    <button class="btn btn-secondary" onclick="exportCSV('all')">📤 Экспорт всей базы в CSV</button>
                    <button class="btn btn-secondary" onclick="exportCSV('individual')">📤 Экспорт только Физлиц</button>
                    <button class="btn btn-secondary" onclick="exportCSV('business')">📤 Экспорт только Юрлиц</button>
                </div>
            </div>
        </div>
    </main>

    <!-- Modal: Add / Edit Client -->
    <div id="client-modal" class="modal-overlay">
        <div class="modal">
            <div class="modal-title" id="client-modal-title">Новый клиент / объект</div>
            <input type="hidden" id="modal-client-id">
            
            <div class="form-group">
                <label>Имя клиента / Название компании / Объекта *</label>
                <input type="text" id="modal-name" placeholder="Например: Иванов Сергей (Коттедж) или ООО 'СпецМаш'">
            </div>

            <div class="form-row">
                <div class="form-group">
                    <label>Номер телефона</label>
                    <input type="text" id="modal-phone" placeholder="+7 (999) 000-00-00">
                </div>
                <div class="form-group">
                    <label>Тип клиента</label>
                    <select id="modal-type">
                        <option value="individual">🏡 Физлицо (Дом / Коттедж / Дача)</option>
                        <option value="business">🏢 Юрлицо (Бизнес / Склад / Магазин)</option>
                        <option value="partner">🤝 Партнер (Прораб / Электрик)</option>
                    </select>
                </div>
            </div>

            <div class="form-row">
                <div class="form-group">
                    <label>Год установки системы</label>
                    <input type="number" id="modal-year" value="2018" min="2010" max="2026">
                </div>
                <div class="form-group">
                    <label>Количество камер</label>
                    <input type="number" id="modal-cameras" value="4">
                </div>
            </div>

            <div class="form-row">
                <div class="form-group">
                    <label>Тип системы</label>
                    <select id="modal-system">
                        <option value="analog">Аналог (AHD / TVI / CVI)</option>
                        <option value="ip">IP видеонаблюдение</option>
                        <option value="hybrid">Гибридная</option>
                        <option value="other">СКУД / Wi-Fi / Другое</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Статус в воронке</label>
                    <select id="modal-status">
                        <option value="new">Новый / Не обработан</option>
                        <option value="contacted">Установлен контакт</option>
                        <option value="offer_sent">Оффер / КП отправлен</option>
                        <option value="upgraded">Модернизирован</option>
                        <option value="on_service">На ТО (обслуживании)</option>
                    </select>
                </div>
            </div>

            <div class="form-group">
                <label>Интерес к поставкам из Китая / Гонконга</label>
                <select id="modal-china">
                    <option value="unknown">Неизвестно / Не обсуждалось</option>
                    <option value="yes">Есть интерес (закупают оборудование)</option>
                    <option value="quote_requested">Запросили расчет стоимости</option>
                    <option value="no">Нет потребности</option>
                </select>
            </div>

            <div class="form-group">
                <label>Адрес объекта</label>
                <input type="text" id="modal-address" placeholder="Город, улица, номер дома / СНТ">
            </div>

            <div class="form-group">
                <label>Заметки по оборудованию и клиенту</label>
                <textarea id="modal-notes" rows="3" placeholder="Какой регистратор стоит, пожелания, жалобы, что нужно предложить..."></textarea>
            </div>

            <div class="modal-actions">
                <button class="btn btn-secondary" onclick="closeClientModal()">Отмена</button>
                <button class="btn btn-success" onclick="saveClient()">Сохранить клиента</button>
            </div>
        </div>
    </div>

    <!-- Modal: Send Offer to Client -->
    <div id="offer-modal" class="modal-overlay">
        <div class="modal" style="width: 700px;">
            <div class="modal-title">✉️ Отправка персонального предложения</div>
            <div id="offer-modal-client-info" style="color: var(--accent); font-size: 14px; margin-bottom: 12px;"></div>
            
            <div class="form-group">
                <label>Выберите шаблон:</label>
                <select id="offer-template-select" onchange="renderOfferForSelectedClient()">
                    <!-- Options populated via JS -->
                </select>
            </div>

            <div class="form-group">
                <label>Готовый персонализированный текст:</label>
                <textarea id="offer-generated-text" rows="10" style="font-size: 13px; line-height: 1.5;"></textarea>
            </div>

            <div class="modal-actions">
                <button class="btn btn-secondary" onclick="closeOfferModal()">Закрыть</button>
                <button class="btn btn-secondary" onclick="copyOfferText()">📋 Скопировать текст</button>
                <button class="btn btn-success" onclick="openWhatsApp()">📲 Открыть в WhatsApp</button>
            </div>
        </div>
    </div>

    <!-- Toast -->
    <div id="toast">Успешно!</div>

    <script>
        let currentClients = [];
        let currentTemplates = [];
        let activeOfferClient = null;

        // Navigation
        function switchTab(tabId) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));
            
            document.getElementById(tabId).classList.add('active');
            event.currentTarget.classList.add('active');

            if (tabId === 'tab-calculators') {
                recalcCctv();
                recalcChina();
            }
        }

        function showToast(msg) {
            const toast = document.getElementById('toast');
            toast.innerText = msg;
            toast.className = 'show';
            setTimeout(() => { toast.className = toast.className.replace('show', ''); }, 3000);
        }

        // --- API CALLS ---
        async function fetchStats() {
            const res = await fetch('/api/stats');
            const data = await res.json();
            document.getElementById('stat-total').innerText = data.total_clients;
            document.getElementById('stat-ind').innerText = data.individuals;
            document.getElementById('stat-biz').innerText = data.businesses;
            document.getElementById('stat-part').innerText = data.partners;
            document.getElementById('badge-total-clients').innerText = data.total_clients;
            document.getElementById('badge-tasks').innerText = `${data.completed_tasks}/${data.total_tasks}`;
        }

        async function loadClients() {
            const type = document.getElementById('filter-type').value;
            const status = document.getElementById('filter-status').value;
            const search = document.getElementById('search-input').value;

            const res = await fetch(`/api/clients?type=${encodeURIComponent(type)}&status=${encodeURIComponent(status)}&search=${encodeURIComponent(search)}`);
            currentClients = await res.json();

            const tbody = document.getElementById('clients-table-body');
            tbody.innerHTML = '';

            if (currentClients.length === 0) {
                tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 30px;">Ничего не найдено. Нажмите "+ Добавить клиента" или импортируйте базу.</td></tr>`;
                return;
            }

            currentClients.forEach(c => {
                const tr = document.createElement('tr');
                
                let typeBadge = '<span class="badge badge-ind">🏡 Физлицо</span>';
                if (c.client_type === 'business') typeBadge = '<span class="badge badge-biz">🏢 Юрлицо</span>';
                if (c.client_type === 'partner') typeBadge = '<span class="badge badge-part">🤝 Партнер</span>';

                let statusBadge = `<span class="badge badge-status-${c.status}">${getStatusLabel(c.status)}</span>`;

                let chinaInterestBadge = '<span style="color: #64748b;">—</span>';
                if (c.china_interest === 'yes') chinaInterestBadge = '<span style="color: #10b981; font-weight: 600;">✓ Интерес есть</span>';
                if (c.china_interest === 'quote_requested') chinaInterestBadge = '<span style="color: #f59e0b; font-weight: 600;">⚡ Ждет расчет</span>';

                tr.innerHTML = `
                    <td>
                        <strong style="color: #fff;">${escapeHtml(c.name)}</strong>
                        <div style="color: var(--text-muted); font-size: 11px;">${escapeHtml(c.address || 'Адрес не указан')}</div>
                    </td>
                    <td>${escapeHtml(c.phone || '—')}</td>
                    <td>${typeBadge}</td>
                    <td>${c.year_installed || '—'} г.</td>
                    <td>${c.cameras_count || 0} шт. (${escapeHtml(c.system_type)})</td>
                    <td>
                        <select onchange="updateClientStatus(${c.id}, this.value)" style="padding: 4px 6px; font-size: 11px;">
                            <option value="new" ${c.status === 'new' ? 'selected' : ''}>Новый</option>
                            <option value="contacted" ${c.status === 'contacted' ? 'selected' : ''}>Контакт</option>
                            <option value="offer_sent" ${c.status === 'offer_sent' ? 'selected' : ''}>Оффер отправлен</option>
                            <option value="upgraded" ${c.status === 'upgraded' ? 'selected' : ''}>Модернизирован</option>
                            <option value="on_service" ${c.status === 'on_service' ? 'selected' : ''}>На ТО</option>
                        </select>
                    </td>
                    <td>${chinaInterestBadge}</td>
                    <td>
                        <button class="btn btn-sm" onclick="openOfferModal(${c.id})" title="Сформировать оффер">✉️ Оффер</button>
                        <button class="btn btn-secondary btn-sm" onclick="editClient(${c.id})" title="Редактировать">✏️</button>
                        <button class="btn btn-secondary btn-sm" style="color: #ef4444;" onclick="deleteClient(${c.id})" title="Удалить">🗑</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });

            fetchStats();
        }

        function getStatusLabel(s) {
            switch(s) {
                case 'new': return 'Новый';
                case 'contacted': return 'Контакт';
                case 'offer_sent': return 'Оффер';
                case 'upgraded': return 'Апгрейд';
                case 'on_service': return 'На ТО';
                default: return s;
            }
        }

        async function loadTasks() {
            const res = await fetch('/api/tasks');
            const tasks = await res.json();
            const container = document.getElementById('action-tasks-container');
            container.innerHTML = '';

            tasks.forEach(t => {
                const item = document.createElement('div');
                item.className = `plan-item ${t.is_completed ? 'completed' : ''}`;
                item.innerHTML = `
                    <input type="checkbox" class="plan-checkbox" ${t.is_completed ? 'checked' : ''} onchange="toggleTask(${t.id})">
                    <div class="plan-body">
                        <div class="plan-day-tag">День ${t.day_number}</div>
                        <div class="plan-title">${escapeHtml(t.day_title)}</div>
                        <div class="plan-desc">${escapeHtml(t.task_text)}</div>
                    </div>
                `;
                container.appendChild(item);
            });

            fetchStats();
        }

        async function toggleTask(taskId) {
            await fetch(`/api/tasks/toggle?id=${taskId}`, { method: 'POST' });
            loadTasks();
            showToast('Статус задачи обновлен');
        }

        async function loadTemplates() {
            const res = await fetch('/api/templates');
            currentTemplates = await res.json();
            
            const container = document.getElementById('templates-container');
            container.innerHTML = '';

            const select = document.getElementById('offer-template-select');
            select.innerHTML = '';

            currentTemplates.forEach(t => {
                // Render in tab
                const card = document.createElement('div');
                card.className = 'template-card';
                card.innerHTML = `
                    <div class="template-header">
                        <div>
                            <div class="template-title">${escapeHtml(t.title)}</div>
                            <div style="font-size: 11px; color: var(--accent); margin-top: 2px;">Целевая аудитория: ${escapeHtml(t.target_audience)}</div>
                        </div>
                        <button class="btn btn-secondary btn-sm" onclick="copyTextDirect('${escapeForAttr(t.content)}')">📋 Скопировать шаблон</button>
                    </div>
                    <div class="template-text-box">${escapeHtml(t.content)}</div>
                `;
                container.appendChild(card);

                // Option in modal
                const opt = document.createElement('option');
                opt.value = t.code;
                opt.innerText = t.title;
                select.appendChild(opt);
            });
        }

        // --- CLIENT MODAL ACTIONS ---
        function openAddClientModal() {
            document.getElementById('client-modal-title').innerText = 'Добавить нового клиента';
            document.getElementById('modal-client-id').value = '';
            document.getElementById('modal-name').value = '';
            document.getElementById('modal-phone').value = '';
            document.getElementById('modal-type').value = 'individual';
            document.getElementById('modal-year').value = '2018';
            document.getElementById('modal-cameras').value = '4';
            document.getElementById('modal-system').value = 'analog';
            document.getElementById('modal-status').value = 'new';
            document.getElementById('modal-china').value = 'unknown';
            document.getElementById('modal-address').value = '';
            document.getElementById('modal-notes').value = '';
            document.getElementById('client-modal').classList.add('active');
        }

        function editClient(id) {
            const c = currentClients.find(item => item.id === id);
            if (!c) return;

            document.getElementById('client-modal-title').innerText = 'Редактировать клиента';
            document.getElementById('modal-client-id').value = c.id;
            document.getElementById('modal-name').value = c.name || '';
            document.getElementById('modal-phone').value = c.phone || '';
            document.getElementById('modal-type').value = c.client_type || 'individual';
            document.getElementById('modal-year').value = c.year_installed || 2018;
            document.getElementById('modal-cameras').value = c.cameras_count || 4;
            document.getElementById('modal-system').value = c.system_type || 'analog';
            document.getElementById('modal-status').value = c.status || 'new';
            document.getElementById('modal-china').value = c.china_interest || 'unknown';
            document.getElementById('modal-address').value = c.address || '';
            document.getElementById('modal-notes').value = c.notes || '';
            document.getElementById('client-modal').classList.add('active');
        }

        function closeClientModal() {
            document.getElementById('client-modal').classList.remove('active');
        }

        async function saveClient() {
            const id = document.getElementById('modal-client-id').value;
            const data = {
                name: document.getElementById('modal-name').value.trim() || 'Без имени',
                phone: document.getElementById('modal-phone').value.trim(),
                client_type: document.getElementById('modal-type').value,
                year_installed: document.getElementById('modal-year').value,
                cameras_count: document.getElementById('modal-cameras').value,
                system_type: document.getElementById('modal-system').value,
                status: document.getElementById('modal-status').value,
                china_interest: document.getElementById('modal-china').value,
                address: document.getElementById('modal-address').value.trim(),
                notes: document.getElementById('modal-notes').value.trim()
            };

            if (id) {
                await fetch(`/api/clients/update?id=${id}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                showToast('Данные клиента обновлены');
            } else {
                await fetch('/api/clients/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                showToast('Клиент успешно добавлен');
            }

            closeClientModal();
            loadClients();
        }

        async function deleteClient(id) {
            if (!confirm('Вы уверены, что хотите удалить этого клиента из базы?')) return;
            await fetch(`/api/clients/delete?id=${id}`, { method: 'POST' });
            showToast('Клиент удален');
            loadClients();
        }

        async function updateClientStatus(id, newStatus) {
            await fetch(`/api/clients/status?id=${id}&status=${encodeURIComponent(newStatus)}`, { method: 'POST' });
            showToast('Статус обновлен');
            fetchStats();
        }

        // --- OFFER MODAL ---
        function openOfferModal(clientId) {
            const client = currentClients.find(c => c.id === clientId);
            if (!client) return;

            activeOfferClient = client;
            document.getElementById('offer-modal-client-info').innerText = `Клиент: ${client.name} | Тел: ${client.phone || 'нет'} | Установлено: ${client.year_installed || '—'}г. (${client.cameras_count} камер)`;

            // Select smart default template based on client type
            const select = document.getElementById('offer-template-select');
            if (client.client_type === 'individual') select.value = 'offer_individual_night_ai';
            else if (client.client_type === 'business') select.value = 'offer_business_analytics';
            else if (client.client_type === 'partner') select.value = 'partner_electrician_offer';

            renderOfferForSelectedClient();
            document.getElementById('offer-modal').classList.add('active');
        }

        function closeOfferModal() {
            document.getElementById('offer-modal').classList.remove('active');
        }

        async function renderOfferForSelectedClient() {
            if (!activeOfferClient) return;
            const code = document.getElementById('offer-template-select').value;
            const res = await fetch(`/api/templates/render?code=${encodeURIComponent(code)}&client_id=${activeOfferClient.id}`);
            const data = await res.json();
            document.getElementById('offer-generated-text').value = data.text;
        }

        function copyOfferText() {
            const text = document.getElementById('offer-generated-text').value;
            navigator.clipboard.writeText(text);
            showToast('Текст скопирован в буфер обмена!');
        }

        function openWhatsApp() {
            if (!activeOfferClient || !activeOfferClient.phone) {
                alert('У клиента не указан номер телефона');
                return;
            }
            const phoneClean = activeOfferClient.phone.replace(/[^0-9]/g, '');
            const text = document.getElementById('offer-generated-text').value;
            const url = `https://wa.me/${phoneClean}?text=${encodeURIComponent(text)}`;
            window.open(url, '_blank');
        }

        // --- IMPORT & EXPORT ---
        async function executeImport() {
            const csvText = document.getElementById('import-csv-area').value.trim();
            if (!csvText) {
                alert('Вставьте данные для импорта');
                return;
            }
            const res = await fetch('/api/clients/import', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ csv_text: csvText })
            });
            const data = await res.json();
            showToast(`Импортировано записей: ${data.imported_count}`);
            document.getElementById('import-csv-area').value = '';
            switchTab('tab-clients');
            loadClients();
        }

        function exportCSV(type) {
            window.open(`/api/clients/export?type=${type}`, '_blank');
        }

        // --- CALCULATORS ---
        function recalcCctv() {
            const cams = parseInt(document.getElementById('calc-cctv-cams').value) || 0;
            const camPrice = parseFloat(document.getElementById('calc-cctv-cam-price').value) || 0;
            const nvrPrice = parseFloat(document.getElementById('calc-cctv-nvr-price').value) || 0;
            const workPrice = parseFloat(document.getElementById('calc-cctv-work').value) || 0;
            const discountPercent = parseFloat(document.getElementById('calc-cctv-discount').value) || 0;

            const equipTotal = (cams * camPrice) + nvrPrice;
            const workTotal = cams * workPrice;
            const subtotal = equipTotal + workTotal;
            const discountTotal = subtotal * (discountPercent / 100);
            const total = subtotal - discountTotal;

            document.getElementById('res-cctv-equip').innerText = equipTotal.toLocaleString() + ' руб.';
            document.getElementById('res-cctv-work').innerText = workTotal.toLocaleString() + ' руб.';
            document.getElementById('res-cctv-discount').innerText = '-' + Math.round(discountTotal).toLocaleString() + ' руб.';
            document.getElementById('res-cctv-total').innerText = Math.round(total).toLocaleString() + ' руб.';
        }

        function recalcChina() {
            const yuan = parseFloat(document.getElementById('calc-china-yuan').value) || 0;
            const yuanRate = parseFloat(document.getElementById('calc-china-rate').value) || 0;
            const weight = parseFloat(document.getElementById('calc-china-weight').value) || 0;
            const tariffUsd = parseFloat(document.getElementById('calc-china-tariff-usd').value) || 0;
            const usdRate = parseFloat(document.getElementById('calc-usd-rate').value) || 0;
            const marginPercent = parseFloat(document.getElementById('calc-china-margin').value) || 0;

            const goodsRub = yuan * yuanRate;
            const shippingRub = weight * tariffUsd * usdRate;
            const baseCost = goodsRub + shippingRub;
            const commission = baseCost * (marginPercent / 100);
            const total = baseCost + commission;

            document.getElementById('res-china-goods').innerText = Math.round(goodsRub).toLocaleString() + ' руб.';
            document.getElementById('res-china-shipping').innerText = Math.round(shippingRub).toLocaleString() + ' руб.';
            document.getElementById('res-china-commission').innerText = Math.round(commission).toLocaleString() + ' руб.';
            document.getElementById('res-china-total').innerText = Math.round(total).toLocaleString() + ' руб.';
        }

        // --- UTILS ---
        function escapeHtml(str) {
            if (!str) return '';
            return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        function escapeForAttr(str) {
            if (!str) return '';
            return encodeURIComponent(str);
        }

        function copyTextDirect(encodedText) {
            const text = decodeURIComponent(encodedText);
            navigator.clipboard.writeText(text);
            showToast('Шаблон скопирован в буфер обмена!');
        }

        // Init on load
        window.onload = () => {
            loadClients();
            loadTasks();
            loadTemplates();
            recalcCctv();
            recalcChina();
        };
    </script>
</body>
</html>
"""

class SuiteRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress noisy standard logs
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
            return

        elif path == "/app_icon.png":
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.png")
            if os.path.exists(icon_path):
                self.send_response(200)
                self.send_header("Content-type", "image/png")
                self.end_headers()
                with open(icon_path, "rb") as f:
                    self.wfile.write(f.read())
                return

        elif path == "/api/stats":
            stats = db.get_stats()
            self._send_json(stats)
            return

        elif path == "/api/clients":
            client_type = query.get("type", ["all"])[0]
            status = query.get("status", ["all"])[0]
            search = query.get("search", [""])[0]
            clients = db.get_clients(client_type=client_type, status=status, search=search)
            self._send_json(clients)
            return

        elif path == "/api/tasks":
            tasks = db.get_action_tasks()
            self._send_json(tasks)
            return

        elif path == "/api/templates":
            templates = db.get_templates()
            self._send_json(templates)
            return

        elif path == "/api/templates/render":
            code = query.get("code", [""])[0]
            client_id = int(query.get("client_id", ["0"])[0])
            rendered = db.render_template_for_client(code, client_id)
            self._send_json({"text": rendered})
            return

        elif path == "/api/clients/export":
            client_type = query.get("type", ["all"])[0]
            csv_data = db.export_to_csv_text(client_type=client_type if client_type != 'all' else None)
            self.send_response(200)
            self.send_header("Content-type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", f"attachment; filename=clients_{client_type}.csv")
            self.end_headers()
            self.wfile.write(csv_data.encode("utf-8-sig"))
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b""

        if path == "/api/clients/add":
            data = json.loads(post_data.decode("utf-8"))
            client_id = db.add_client(data)
            self._send_json({"success": True, "id": client_id})
            return

        elif path == "/api/clients/update":
            client_id = int(query.get("id", ["0"])[0])
            data = json.loads(post_data.decode("utf-8"))
            success = db.update_client(client_id, data)
            self._send_json({"success": success})
            return

        elif path == "/api/clients/status":
            client_id = int(query.get("id", ["0"])[0])
            status = query.get("status", ["new"])[0]
            success = db.update_client_status(client_id, status)
            self._send_json({"success": success})
            return

        elif path == "/api/clients/delete":
            client_id = int(query.get("id", ["0"])[0])
            success = db.delete_client(client_id)
            self._send_json({"success": success})
            return

        elif path == "/api/tasks/toggle":
            task_id = int(query.get("id", ["0"])[0])
            success = db.toggle_task(task_id)
            self._send_json({"success": success})
            return

        elif path == "/api/clients/import":
            data = json.loads(post_data.decode("utf-8"))
            csv_text = data.get("csv_text", "")
            count = db.import_from_csv_text(csv_text)
            self._send_json({"success": True, "imported_count": count})
            return

        self.send_error(404, "Not Found")

    def _send_json(self, data: Any):
        self.send_response(200)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

def start_server(port: int = 8765, open_browser: bool = True):
    try:
        server = HTTPServer(("127.0.0.1", port), SuiteRequestHandler)
    except OSError as exc:
        print("============================================================")
        print("ОШИБКА: не удалось запустить сервер на порту", port)
        print("Причина:", exc)
        print()
        print("Что попробовать:")
        print("  1. Закройте другое окно этой же программы")
        print("  2. Подождите минуту и запустите снова")
        print("  3. Перезагрузите компьютер")
        print("============================================================")
        raise SystemExit(1) from exc

    print("============================================================")
    print("Программа управления бизнесом запущена!")
    print(f"Откройте в браузере: http://localhost:{port}")
    print("Чтобы остановить — закройте это окно.")
    print("============================================================")

    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановка сервера...")
        server.server_close()

if __name__ == "__main__":
    start_server(port=8765, open_browser=True)
