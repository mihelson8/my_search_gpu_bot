"""SQLite storage for own/foreign vehicles and recognition events."""

from __future__ import annotations

import csv
import io
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from anpr.plates import category_label, normalize_plate, parse_category

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "anpr_data")
DEFAULT_DB_PATH = os.path.join(DATA_DIR, "anpr.db")


class AnprDB:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        directory = os.path.dirname(os.path.abspath(self.db_path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS vehicles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plate TEXT NOT NULL,
                    plate_normalized TEXT NOT NULL UNIQUE,
                    owner_name TEXT,
                    category TEXT NOT NULL DEFAULT 'own',
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plate TEXT NOT NULL,
                    plate_normalized TEXT NOT NULL,
                    category TEXT NOT NULL,
                    confidence REAL DEFAULT 0,
                    source TEXT,
                    screenshot_path TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_plate ON events(plate_normalized)"
            )
            conn.commit()

    def add_vehicle(
        self,
        plate: str,
        category: str = "own",
        owner_name: str = "",
        notes: str = "",
    ) -> int:
        normalized = normalize_plate(plate)
        if not normalized:
            raise ValueError("Пустой номер")
        category = parse_category(category)
        if category not in ("own", "foreign"):
            category = "own"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO vehicles (plate, plate_normalized, owner_name, category, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(plate_normalized) DO UPDATE SET
                    plate = excluded.plate,
                    owner_name = excluded.owner_name,
                    category = excluded.category,
                    notes = excluded.notes,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (plate.strip().upper(), normalized, owner_name.strip(), category, notes.strip()),
            )
            conn.commit()
            cursor.execute("SELECT id FROM vehicles WHERE plate_normalized = ?", (normalized,))
            row = cursor.fetchone()
            return int(row["id"])

    def update_vehicle(self, vehicle_id: int, **fields: Any) -> None:
        allowed = {"plate", "owner_name", "category", "notes"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        if "plate" in updates:
            updates["plate_normalized"] = normalize_plate(updates["plate"])
            updates["plate"] = str(updates["plate"]).strip().upper()
        if "category" in updates:
            updates["category"] = parse_category(str(updates["category"]))
        assignments = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [vehicle_id]
        with self.get_connection() as conn:
            conn.execute(
                f"UPDATE vehicles SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                values,
            )
            conn.commit()

    def delete_vehicle(self, vehicle_id: int) -> None:
        with self.get_connection() as conn:
            conn.execute("DELETE FROM vehicles WHERE id = ?", (vehicle_id,))
            conn.commit()

    def get_vehicles(self, category: Optional[str] = None, search: str = "") -> List[Dict[str, Any]]:
        query = "SELECT * FROM vehicles WHERE 1=1"
        params: List[Any] = []
        if category in ("own", "foreign"):
            query += " AND category = ?"
            params.append(category)
        if search.strip():
            like = f"%{search.strip()}%"
            query += " AND (plate LIKE ? OR plate_normalized LIKE ? OR owner_name LIKE ? OR notes LIKE ?)"
            params.extend([like, like, like, like])
        query += " ORDER BY category ASC, owner_name ASC, plate_normalized ASC"
        with self.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def find_vehicle(self, plate: str) -> Optional[Dict[str, Any]]:
        normalized = normalize_plate(plate)
        if not normalized:
            return None
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM vehicles WHERE plate_normalized = ?",
                (normalized,),
            ).fetchone()
            return dict(row) if row else None

    def classify(self, plate: str, unknown_as_foreign: bool = False) -> Dict[str, Any]:
        vehicle = self.find_vehicle(plate)
        if vehicle:
            return {
                "category": vehicle["category"],
                "label": category_label(vehicle["category"]),
                "vehicle": vehicle,
            }
        category = "foreign" if unknown_as_foreign else "unknown"
        return {
            "category": category,
            "label": category_label(category),
            "vehicle": None,
        }

    def log_event(
        self,
        plate: str,
        category: str,
        confidence: float = 0.0,
        source: str = "",
        screenshot_path: str = "",
        notes: str = "",
    ) -> int:
        normalized = normalize_plate(plate) or plate.strip().upper()
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO events (
                    plate, plate_normalized, category, confidence, source, screenshot_path, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plate.strip().upper(),
                    normalized,
                    category,
                    float(confidence or 0),
                    source,
                    screenshot_path,
                    notes,
                    created_at,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def get_events(self, limit: int = 200, category: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM events WHERE 1=1"
        params: List[Any] = []
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(int(limit))
        with self.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def last_event_for_plate(self, plate: str) -> Optional[Dict[str, Any]]:
        normalized = normalize_plate(plate)
        if not normalized:
            return None
        with self.get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM events
                WHERE plate_normalized = ?
                ORDER BY id DESC LIMIT 1
                """,
                (normalized,),
            ).fetchone()
            return dict(row) if row else None

    def event_is_duplicate(self, plate: str, window_sec: int = 30) -> bool:
        last = self.last_event_for_plate(plate)
        if not last:
            return False
        try:
            created = datetime.fromisoformat(str(last["created_at"]))
        except ValueError:
            return False
        delta = datetime.now() - created
        return delta.total_seconds() < window_sec

    def stats(self) -> Dict[str, int]:
        with self.get_connection() as conn:
            own = conn.execute("SELECT COUNT(*) FROM vehicles WHERE category = 'own'").fetchone()[0]
            foreign = conn.execute(
                "SELECT COUNT(*) FROM vehicles WHERE category = 'foreign'"
            ).fetchone()[0]
            events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return {"own": int(own), "foreign": int(foreign), "events": int(events)}

    def export_vehicles_csv(self) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["plate", "owner_name", "category", "notes"])
        for row in self.get_vehicles():
            writer.writerow(
                [row["plate_normalized"], row["owner_name"] or "", row["category"], row["notes"] or ""]
            )
        return output.getvalue()

    def import_vehicles_csv(self, text: str) -> int:
        reader = csv.DictReader(io.StringIO(text))
        count = 0
        for row in reader:
            plate = (row.get("plate") or row.get("номер") or "").strip()
            if not plate:
                continue
            self.add_vehicle(
                plate=plate,
                category=row.get("category") or row.get("категория") or "own",
                owner_name=row.get("owner_name") or row.get("владелец") or "",
                notes=row.get("notes") or row.get("заметки") or "",
            )
            count += 1
        return count
