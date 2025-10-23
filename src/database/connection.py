# src/database/connection.py
import sqlite3
import os
import logging

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))
os.makedirs(BASE_DIR, exist_ok=True)

DB_PATH = os.path.join(BASE_DIR, "main.db")

if not os.access(BASE_DIR, os.W_OK):
    raise PermissionError(f"❌ Нет прав на запись в {BASE_DIR}")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            balance INTEGER DEFAULT 0,
            xp INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()
    logging.info(f"📦 База данных инициализирована: {DB_PATH}")
