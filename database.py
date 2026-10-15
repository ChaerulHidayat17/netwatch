import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "netmonitor.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Devices table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                ip TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL DEFAULT 'other',
                location TEXT DEFAULT '',
                status TEXT DEFAULT 'UNKNOWN',
                latency REAL DEFAULT 0.0,
                last_seen TEXT,
                last_checked TEXT,
                consecutive_fails INTEGER DEFAULT 0,
                down_since TEXT,
                enabled INTEGER DEFAULT 1,
                alert_enabled INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Ensure alert_enabled column exists for existing DBs
        cursor.execute("PRAGMA table_info(devices)")
        cols = [col["name"] for col in cursor.fetchall()]
        if "alert_enabled" not in cols:
            cursor.execute("ALTER TABLE devices ADD COLUMN alert_enabled INTEGER DEFAULT 1")
        
        # Settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        # Incidents / Logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER,
                device_name TEXT,
                ip TEXT,
                category TEXT,
                event_type TEXT,
                message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Default settings
        defaults = {
            "telegram_bot_token": "",
            "telegram_chat_id": "",
            "ping_interval": "15",
            "fail_threshold": "2",
            "telegram_enabled": "1"
        }
        for k, v in defaults.items():
            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
            
        conn.commit()

def get_settings():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM settings")
        rows = cursor.fetchall()
        return {r["key"]: r["value"] for r in rows}

def update_settings(settings_dict):
    with get_db() as conn:
        cursor = conn.cursor()
        for k, v in settings_dict.items():
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
        conn.commit()

def log_incident(device_id, device_name, ip, category, event_type, message):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO incidents (device_id, device_name, ip, category, event_type, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
        """, (device_id, device_name, ip, category, event_type, message))
        conn.commit()
