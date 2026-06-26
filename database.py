"""
SQLite database layer -> accounts, trans act history.... (replaces fixed-size limit by esp32 ram)
"""

import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "tollway.db")

DEFAULT_BALANCE = 2000    
EXIT_COST = 150          
# ARCHIEVE MUNA KASI MAY MATRIX NA::
SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    vehicle_number INTEGER PRIMARY KEY AUTOINCREMENT,
    rfid_uid        TEXT UNIQUE NOT NULL,
    balance         INTEGER NOT NULL DEFAULT 2000,
    is_inside       INTEGER NOT NULL DEFAULT 0,
    entry_lane      TEXT
);

CREATE INDEX IF NOT EXISTS idx_accounts_rfid ON accounts(rfid_uid);

CREATE TABLE IF NOT EXISTS transaction_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_number  INTEGER NOT NULL,
    lane_id         TEXT NOT NULL,
    gate_type       TEXT NOT NULL,
    amount_charged  INTEGER NOT NULL,
    timestamp       TEXT NOT NULL,
    FOREIGN KEY (vehicle_number) REFERENCES accounts(vehicle_number)
);
"""


class TollwayDB:
    def __init__(self, db_path: str = DB_PATH, reset: bool = False):
        if reset and os.path.exists(db_path):
            os.remove(db_path)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.executescript(SCHEMA)
        self._migrate_entry_lane_column()
        self.conn.commit()

    def _migrate_entry_lane_column(self):
        """CREATE TABLE IF NOT EXISTS AUTOMATICS OMCM"""
        try:
            self.conn.execute("ALTER TABLE accounts ADD COLUMN entry_lane TEXT")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                raise

    def close(self):
        self.conn.close()

    # ---------------- Accountss ----------------

    def find_by_uid(self, rfid_uid: str):
        cur = self.conn.execute(
            "SELECT * FROM accounts WHERE rfid_uid = ?", (rfid_uid,)
        )
        return cur.fetchone()

    def find_by_vehicle_number(self, vehicle_number: int):
        cur = self.conn.execute(
            "SELECT * FROM accounts WHERE vehicle_number = ?", (vehicle_number,)
        )
        return cur.fetchone()

    def register_account(self, rfid_uid: str, is_inside: bool = True,
                          balance: int = DEFAULT_BALANCE, entry_lane: str = None):
        """first tap at ENTRY creates the row, same sa getOrCreateVehicleIndex() did in prototype 1.2."""
        cur = self.conn.execute(
            "INSERT INTO accounts (rfid_uid, balance, is_inside, entry_lane) VALUES (?, ?, ?, ?)",
            (rfid_uid, balance, 1 if is_inside else 0, entry_lane),
        )
        self.conn.commit()
        return self.find_by_vehicle_number(cur.lastrowid)

    def set_inside(self, vehicle_number: int, is_inside: bool):
        self.conn.execute(
            "UPDATE accounts SET is_inside = ? WHERE vehicle_number = ?",
            (1 if is_inside else 0, vehicle_number),
        )
        self.conn.commit()

    def set_entry_lane(self, vehicle_number: int, entry_lane: str):
        self.conn.execute(
            "UPDATE accounts SET entry_lane = ? WHERE vehicle_number = ?",
            (entry_lane, vehicle_number),
        )
        self.conn.commit()

    def adjust_balance(self, vehicle_number: int, delta: int):
        self.conn.execute(
            "UPDATE accounts SET balance = balance + ? WHERE vehicle_number = ?",
            (delta, vehicle_number),
        )
        self.conn.commit()
        return self.find_by_vehicle_number(vehicle_number)

    def dump_all(self):
        cur = self.conn.execute("SELECT * FROM accounts ORDER BY vehicle_number")
        return cur.fetchall()

    # ---------------- Transaction history ----------------

    def log_transaction(self, vehicle_number: int, lane_id: str,
                         gate_type: str, amount_charged: int):
        self.conn.execute(
            "INSERT INTO transaction_history "
            "(vehicle_number, lane_id, gate_type, amount_charged, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (vehicle_number, lane_id, gate_type, amount_charged,
             datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

    def dump_transactions(self):
        cur = self.conn.execute(
            "SELECT * FROM transaction_history ORDER BY id"
        )
        return cur.fetchall()
