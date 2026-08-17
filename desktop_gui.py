"""
Desktop Tkinter GUI for CCTV & China Business Suite.
Works completely standalone without any external web dependencies.
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import webbrowser
import urllib.parse
from business_suite_db import BusinessDB

class BusinessSuiteApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CCTV & China Cargo Business Suite — Пульт управления")
        self.root.geometry("1100x700")
        self.root.minsize(900, 600)

        self.db = BusinessDB()
        if len(self.db.get_clients()) == 0:
            self.db.seed_demo_clients()

        self._setup_styles()
        self._create_widgets()
        self.refresh_all()

    def _setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        # Configure darkish modern palette
        self.bg_dark = "#0f172a"
        self.card_bg = "#1e293b"
        self.accent_blue = "#2563eb"
        self.text_white = "#f8fafc"
        self.text_muted = "#94a3b8"

        self.root.configure(bg=self.bg_dark)
        
        self.style.configure("TFrame", background=self.bg_dark)
        self.style.configure("Card.TFrame", background=self.card_bg)
        self.style.configure("TLabel", background=self.bg_dark, foreground=self.text_white, font=("Segoe UI", 10))
        self.style.configure("Card.TLabel", background=self.card_bg, foreground=self.text_white, font=("Segoe UI", 10))
        self.style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"), foreground="#38bdf8")
        self.style.configure("TButton", font=("Segoe UI", 9, "bold"), padding=6)
        self.style.configure("Treeview", font=("Segoe UI", 9), rowheight=26)
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def _create_widgets(self):
        # Top Header & Stats Bar
        header_frame = ttk.Frame(self.root, padding="15 10")
        header_frame.pack(fill="x")

        title_label = ttk.Label(header_frame, text="📹 🇨🇳 CCTV & China Cargo Business Suite", style="Header.TLabel")
        title_label.pack(side="left")

        self.stats_label = ttk.Label(header_frame, text="Загрузка статистики...", foreground="#38bdf8", font=("Segoe UI", 10, "bold"))
        self.stats_label.pack(side="right")

        # Notebook tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=15, pady=10)

        # Tab 1: Clients DB
        self.tab_clients = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_clients, text=" 👥 База клиентов (с 2016 г.) ")
        self._build_clients_tab()

        # Tab 2: 7-Day Action Plan
        self.tab_plan = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_plan, text=" 📅 План действий на 7 дней ")
        self._build_plan_tab()

        # Tab 3: Offer Templates & Generator
        self.tab_offers = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_offers, text=" 💬 Готовые офферы & Скрипты ")
        self._build_offers_tab()

        # Tab 4: Calculators (CCTV & China)
        self.tab_calc = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_calc, text=" 🧮 Экспресс-калькуляторы ")
        self._build_calc_tab()

    # --- TAB 1: CLIENTS ---
    def _build_clients_tab(self):
        top_bar = ttk.Frame(self.tab_clients)
        top_bar.pack(fill="x", pady=(0, 10))

        ttk.Label(top_bar, text="Поиск:").pack(side="left", padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.load_clients())
        ttk.Entry(top_bar, textvariable=self.search_var, width=25).pack(side="left", padx=(0, 15))

        ttk.Label(top_bar, text="Тип:").pack(side="left", padx=(0, 5))
        self.filter_type_var = tk.StringVar(value="all")
        type_cb = ttk.Combobox(top_bar, textvariable=self.filter_type_var, values=["all", "individual", "business", "partner"], state="readonly", width=12)
        type_cb.pack(side="left", padx=(0, 15))
        type_cb.bind("<<ComboboxSelected>>", lambda e: self.load_clients())

        btn_add = ttk.Button(top_bar, text="+ Добавить клиента", command=self.open_add_client_dialog)
        btn_add.pack(side="right", padx=5)

        btn_offer = ttk.Button(top_bar, text="✉️ Сформировать оффер", command=self.generate_offer_for_selected)
        btn_offer.pack(side="right", padx=5)

        btn_del = ttk.Button(top_bar, text="🗑 Удалить", command=self.delete_selected_client)
        btn_del.pack(side="right", padx=5)

        # Clients Table
        columns = ("id", "name", "phone", "type", "year", "cameras", "status", "china")
        self.tree_clients = ttk.Treeview(self.tab_clients, columns=columns, show="headings", selectmode="browse")
        
        self.tree_clients.heading("id", text="ID")
        self.tree_clients.heading("name", text="Имя / Объект")
        self.tree_clients.heading("phone", text="Телефон")
        self.tree_clients.heading("type", text="Тип")
        self.tree_clients.heading("year", text="Год")
        self.tree_clients.heading("cameras", text="Камер")
        self.tree_clients.heading("status", text="Статус")
        self.tree_clients.heading("china", text="Китай/Гонконг")

        self.tree_clients.column("id", width=40, anchor="center")
        self.tree_clients.column("name", width=220)
        self.tree_clients.column("phone", width=140)
        self.tree_clients.column("type", width=100)
        self.tree_clients.column("year", width=60, anchor="center")
        self.tree_clients.column("cameras", width=60, anchor="center")
        self.tree_clients.column("status", width=110)
        self.tree_clients.column("china", width=120)

        scrollbar = ttk.Scrollbar(self.tab_clients, orient="vertical", command=self.tree_clients.yview)
        self.tree_clients.configure(yscrollcommand=scrollbar.set)

        self.tree_clients.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    # --- TAB 2: 7-DAY PLAN ---
    def _build_plan_tab(self):
        info_label = ttk.Label(self.tab_plan, text="План действий на первые 7 дней для запуска продаж и масштабирования.\nОтмечайте выполненные пункты галочками:", justify="left")
        info_label.pack(anchor="w", pady=(0, 10))

        self.tasks_container = ttk.Frame(self.tab_plan)
        self.tasks_container.pack(fill="both", expand=True)

    # --- TAB 3: OFFERS ---
    def _build_offers_tab(self):
        top_frame = ttk.Frame(self.tab_offers)
        top_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(top_frame, text="Шаблон:").pack(side="left", padx=(0, 5))
        self.template_var = tk.StringVar()
        self.combo_templates = ttk.Combobox(top_frame, textvariable=self.template_var, state="readonly", width=45)
        self.combo_templates.pack(side="left", padx=(0, 15))
        self.combo_templates.bind("<<ComboboxSelected>>", self._on_template_selected)

        btn_copy = ttk.Button(top_frame, text="📋 Скопировать текст", command=self._copy_offer_text)
        btn_copy.pack(side="right", padx=5)

        self.txt_offer = tk.Text(self.tab_offers, wrap="word", font=("Segoe UI", 11), bg="#1e293b", fg="#f8fafc", insertbackground="#fff", padx=10, pady=10)
        self.txt_offer.pack(fill="both", expand=True)

    # --- TAB 4: CALCULATORS ---
    def _build_calc_tab(self):
        container = ttk.Frame(self.tab_calc)
        container.pack(fill="both", expand=True)

        # Left: CCTV Calc
        cctv_frame = ttk.LabelFrame(container, text=" 📹 Расчет модернизации видеонаблюдения ", padding=15)
        cctv_frame.pack(side="left", fill="both", expand=True, padx=5)

        ttk.Label(cctv_frame, text="Количество камер:").grid(row=0, column=0, sticky="w", pady=4)
        self.calc_cams_entry = ttk.Entry(cctv_frame)
        self.calc_cams_entry.insert(0, "4")
        self.calc_cams_entry.grid(row=0, column=1, pady=4)

        ttk.Label(cctv_frame, text="Цена камеры (руб):").grid(row=1, column=0, sticky="w", pady=4)
        self.calc_cam_price_entry = ttk.Entry(cctv_frame)
        self.calc_cam_price_entry.insert(0, "4500")
        self.calc_cam_price_entry.grid(row=1, column=1, pady=4)

        ttk.Label(cctv_frame, text="Регистратор + HDD (руб):").grid(row=2, column=0, sticky="w", pady=4)
        self.calc_nvr_price_entry = ttk.Entry(cctv_frame)
        self.calc_nvr_price_entry.insert(0, "16000")
        self.calc_nvr_price_entry.grid(row=2, column=1, pady=4)

        ttk.Label(cctv_frame, text="Монтаж за точку (руб):").grid(row=3, column=0, sticky="w", pady=4)
        self.calc_work_entry = ttk.Entry(cctv_frame)
        self.calc_work_entry.insert(0, "1800")
        self.calc_work_entry.grid(row=3, column=1, pady=4)

        ttk.Label(cctv_frame, text="Скидка Trade-in (%):").grid(row=4, column=0, sticky="w", pady=4)
        self.calc_discount_entry = ttk.Entry(cctv_frame)
        self.calc_discount_entry.insert(0, "15")
        self.calc_discount_entry.grid(row=4, column=1, pady=4)

        btn_cctv_calc = ttk.Button(cctv_frame, text="Рассчитать сумму", command=self.run_cctv_calc)
        btn_cctv_calc.grid(row=5, column=0, columnspan=2, pady=12)

        self.cctv_res_label = ttk.Label(cctv_frame, text="ИТОГО КЛИЕНТУ: 0 руб.", font=("Segoe UI", 12, "bold"), foreground="#38bdf8")
        self.cctv_res_label.grid(row=6, column=0, columnspan=2, pady=5)

        # Right: China Logistics Calc
        china_frame = ttk.LabelFrame(container, text=" 🇨🇳 Расчет доставки из Китая / Гонконга ", padding=15)
        china_frame.pack(side="right", fill="both", expand=True, padx=5)

        ttk.Label(china_frame, text="Стоимость товара (¥ Юани):").grid(row=0, column=0, sticky="w", pady=4)
        self.calc_yuan_entry = ttk.Entry(china_frame)
        self.calc_yuan_entry.insert(0, "10000")
        self.calc_yuan_entry.grid(row=0, column=1, pady=4)

        ttk.Label(china_frame, text="Курс CNY/RUB (₽):").grid(row=1, column=0, sticky="w", pady=4)
        self.calc_cny_rate_entry = ttk.Entry(china_frame)
        self.calc_cny_rate_entry.insert(0, "13.8")
        self.calc_cny_rate_entry.grid(row=1, column=1, pady=4)

        ttk.Label(china_frame, text="Вес груза (кг):").grid(row=2, column=0, sticky="w", pady=4)
        self.calc_weight_entry = ttk.Entry(china_frame)
        self.calc_weight_entry.insert(0, "45")
        self.calc_weight_entry.grid(row=2, column=1, pady=4)

        ttk.Label(china_frame, text="Тариф за кг ($ USD):").grid(row=3, column=0, sticky="w", pady=4)
        self.calc_tariff_entry = ttk.Entry(china_frame)
        self.calc_tariff_entry.insert(0, "4.5")
        self.calc_tariff_entry.grid(row=3, column=1, pady=4)

        ttk.Label(china_frame, text="Курс USD/RUB (₽):").grid(row=4, column=0, sticky="w", pady=4)
        self.calc_usd_rate_entry = ttk.Entry(china_frame)
        self.calc_usd_rate_entry.insert(0, "95.0")
        self.calc_usd_rate_entry.grid(row=4, column=1, pady=4)

        ttk.Label(china_frame, text="Комиссия выкупа (%):").grid(row=5, column=0, sticky="w", pady=4)
        self.calc_margin_entry = ttk.Entry(china_frame)
        self.calc_margin_entry.insert(0, "10")
        self.calc_margin_entry.grid(row=5, column=1, pady=4)

        btn_china_calc = ttk.Button(china_frame, text="Рассчитать себестоимость", command=self.run_china_calc)
        btn_china_calc.grid(row=6, column=0, columnspan=2, pady=12)

        self.china_res_label = ttk.Label(china_frame, text="ИТОГО КЛИЕНТУ: 0 руб.", font=("Segoe UI", 12, "bold"), foreground="#f59e0b")
        self.china_res_label.grid(row=7, column=0, columnspan=2, pady=5)

    # --- REFRESH DATA ---
    def refresh_all(self):
        self.load_stats()
        self.load_clients()
        self.load_plan()
        self.load_templates()
        self.run_cctv_calc()
        self.run_china_calc()

    def load_stats(self):
        stats = self.db.get_stats()
        self.stats_label.config(
            text=f"Всего клиентов: {stats['total_clients']} | Физлица: {stats['individuals']} | Юрлица: {stats['businesses']} | План 7 дней: {stats['completed_tasks']}/{stats['total_tasks']}"
        )

    def load_clients(self):
        for item in self.tree_clients.get_children():
            self.tree_clients.delete(item)

        search = self.search_var.get().strip()
        client_type = self.filter_type_var.get()
        clients = self.db.get_clients(client_type=client_type, search=search)

        for c in clients:
            type_str = "Физлицо" if c['client_type'] == 'individual' else ("Юрлицо" if c['client_type'] == 'business' else "Партнер")
            china_str = "✓ Интерес" if c['china_interest'] == 'yes' else ("⚡ Ждет КП" if c['china_interest'] == 'quote_requested' else "—")
            
            self.tree_clients.insert("", "end", values=(
                c['id'],
                c['name'],
                c['phone'] or "—",
                type_str,
                c['year_installed'] or "—",
                c['cameras_count'] or 0,
                c['status'],
                china_str
            ))

    def load_plan(self):
        for widget in self.tasks_container.winfo_children():
            widget.destroy()

        tasks = self.db.get_action_tasks()
        for t in tasks:
            frame = ttk.Frame(self.tasks_container, padding=6)
            frame.pack(fill="x", pady=2)

            var = tk.BooleanVar(value=bool(t['is_completed']))
            cb = ttk.Checkbutton(frame, text=f"День {t['day_number']}: {t['day_title']} — {t['task_text']}", variable=var, command=lambda tid=t['id']: self.toggle_task(tid))
            cb.pack(anchor="w")

    def toggle_task(self, task_id):
        self.db.toggle_task(task_id)
        self.load_stats()

    def load_templates(self):
        templates = self.db.get_templates()
        self.templates_dict = {t['title']: t['content'] for t in templates}
        self.combo_templates['values'] = list(self.templates_dict.keys())
        if self.templates_dict:
            first_title = list(self.templates_dict.keys())[0]
            self.combo_templates.set(first_title)
            self._on_template_selected()

    def _on_template_selected(self, event=None):
        title = self.combo_templates.get()
        content = self.templates_dict.get(title, "")
        self.txt_offer.delete("1.0", "end")
        self.txt_offer.insert("1.0", content)

    def _copy_offer_text(self):
        text = self.txt_offer.get("1.0", "end").strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("Успешно", "Текст оффера скопирован в буфер обмена!")

    def generate_offer_for_selected(self):
        selected = self.tree_clients.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите клиента из списка!")
            return

        item = self.tree_clients.item(selected[0])
        client_id = item['values'][0]
        client = self.db.get_client_by_id(client_id)
        if not client:
            return

        self.notebook.select(self.tab_offers)
        
        # Pick template by client type
        code = "offer_individual_night_ai" if client['client_type'] == 'individual' else "offer_business_analytics"
        rendered = self.db.render_template_for_client(code, client_id)
        
        self.txt_offer.delete("1.0", "end")
        self.txt_offer.insert("1.0", rendered)
        messagebox.showinfo("Оффер сформирован", f"Оффер персонализирован для клиента: {client['name']}")

    def open_add_client_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Добавить клиента")
        dlg.geometry("450x450")
        dlg.configure(bg=self.bg_dark)

        ttk.Label(dlg, text="Имя / Объект:").pack(anchor="w", padx=20, pady=(15, 2))
        name_e = ttk.Entry(dlg, width=40)
        name_e.pack(padx=20)

        ttk.Label(dlg, text="Телефон:").pack(anchor="w", padx=20, pady=(10, 2))
        phone_e = ttk.Entry(dlg, width=40)
        phone_e.pack(padx=20)

        ttk.Label(dlg, text="Тип:").pack(anchor="w", padx=20, pady=(10, 2))
        type_e = ttk.Combobox(dlg, values=["individual", "business", "partner"], state="readonly", width=37)
        type_e.set("individual")
        type_e.pack(padx=20)

        ttk.Label(dlg, text="Год монтажа:").pack(anchor="w", padx=20, pady=(10, 2))
        year_e = ttk.Entry(dlg, width=40)
        year_e.insert(0, "2018")
        year_e.pack(padx=20)

        ttk.Label(dlg, text="Количество камер:").pack(anchor="w", padx=20, pady=(10, 2))
        cam_e = ttk.Entry(dlg, width=40)
        cam_e.insert(0, "4")
        cam_e.pack(padx=20)

        def save():
            name = name_e.get().strip() or "Без имени"
            phone = phone_e.get().strip()
            ctype = type_e.get()
            year = int(year_e.get().strip()) if year_e.get().strip().isdigit() else 2018
            cams = int(cam_e.get().strip()) if cam_e.get().strip().isdigit() else 4

            self.db.add_client({
                "name": name,
                "phone": phone,
                "client_type": ctype,
                "year_installed": year,
                "cameras_count": cams
            })
            dlg.destroy()
            self.refresh_all()
            messagebox.showinfo("Успех", "Клиент добавлен!")

        ttk.Button(dlg, text="Сохранить", command=save).pack(pady=20)

    def delete_selected_client(self):
        selected = self.tree_clients.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите клиента из списка!")
            return

        if messagebox.askyesno("Подтверждение", "Удалить выбранного клиента?"):
            item = self.tree_clients.item(selected[0])
            client_id = item['values'][0]
            self.db.delete_client(client_id)
            self.refresh_all()

    def run_cctv_calc(self):
        try:
            cams = int(self.calc_cams_entry.get() or 0)
            cam_price = float(self.calc_cam_price_entry.get() or 0)
            nvr_price = float(self.calc_nvr_price_entry.get() or 0)
            work_price = float(self.calc_work_entry.get() or 0)
            discount = float(self.calc_discount_entry.get() or 0)

            subtotal = (cams * cam_price) + nvr_price + (cams * work_price)
            total = subtotal * (1 - discount / 100)
            self.cctv_res_label.config(text=f"ИТОГО КЛИЕНТУ: {int(total):,} руб.")
        except ValueError:
            pass

    def run_china_calc(self):
        try:
            yuan = float(self.calc_yuan_entry.get() or 0)
            cny_rate = float(self.calc_cny_rate_entry.get() or 0)
            weight = float(self.calc_weight_entry.get() or 0)
            tariff = float(self.calc_tariff_entry.get() or 0)
            usd_rate = float(self.calc_usd_rate_entry.get() or 0)
            margin = float(self.calc_margin_entry.get() or 0)

            base = (yuan * cny_rate) + (weight * tariff * usd_rate)
            total = base * (1 + margin / 100)
            self.china_res_label.config(text=f"ИТОГО КЛИЕНТУ В РФ: {int(total):,} руб.")
        except ValueError:
            pass

def main():
    root = tk.Tk()
    app = BusinessSuiteApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
