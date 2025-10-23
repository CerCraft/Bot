import sqlite3
import os
from datetime import datetime, timedelta


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strike.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_discipline_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            guild_id INTEGER,
            moderator_id INTEGER,
            reason TEXT,
            created_at REAL,
            expire_at REAL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS strikes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            guild_id INTEGER,
            moderator_id INTEGER,
            reason TEXT,
            created_at REAL,
            expire_at REAL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS praises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            guild_id INTEGER,
            moderator_id INTEGER,
            reason TEXT,
            created_at REAL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS punishments_history (
            user_id INTEGER,
            guild_id INTEGER,
            moderator_id INTEGER,
            type TEXT,
            reason TEXT,
            date REAL
        )
        """
    )

    conn.commit()
    conn.close()


def cleanup_expired(now_ts: float | None = None):
    now_ts = now_ts or datetime.utcnow().timestamp()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM warnings WHERE expire_at IS NOT NULL AND expire_at <= ?", (now_ts,))
    cursor.execute("DELETE FROM strikes WHERE expire_at IS NOT NULL AND expire_at <= ?", (now_ts,))
    conn.commit()
    conn.close()


def count_warnings(user_id: int, guild_id: int) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM warnings WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
    c = cursor.fetchone()[0]
    conn.close()
    return int(c or 0)


def count_strikes(user_id: int, guild_id: int) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM strikes WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
    c = cursor.fetchone()[0]
    conn.close()
    return int(c or 0)


def count_praises(user_id: int, guild_id: int) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM praises WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
    c = cursor.fetchone()[0]
    conn.close()
    return int(c or 0)


def _delete_oldest_warnings(user_id: int, guild_id: int, count: int) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM warnings WHERE user_id = ? AND guild_id = ? ORDER BY created_at ASC LIMIT ?",
        (user_id, guild_id, count),
    )
    ids = [row[0] for row in cursor.fetchall()]
    if ids:
        cursor.execute(
            f"DELETE FROM warnings WHERE id IN ({','.join('?' for _ in ids)})",
            ids,
        )
    conn.commit()
    conn.close()
    return len(ids)


def _delete_oldest_praises(user_id: int, guild_id: int, count: int) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM praises WHERE user_id = ? AND guild_id = ? ORDER BY created_at ASC LIMIT ?",
        (user_id, guild_id, count),
    )
    ids = [row[0] for row in cursor.fetchall()]
    if ids:
        cursor.execute(
            f"DELETE FROM praises WHERE id IN ({','.join('?' for _ in ids)})",
            ids,
        )
    conn.commit()
    conn.close()
    return len(ids)


def add_warning(user_id: int, guild_id: int, moderator_id: int, reason: str):
    created = datetime.utcnow()
    expire_at = created + timedelta(days=30)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO warnings (user_id, guild_id, moderator_id, reason, created_at, expire_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, guild_id, moderator_id, reason, created.timestamp(), expire_at.timestamp()),
    )
    conn.commit()
    conn.close()
    # Normalize: convert 3 warnings to 1 strike
    normalize_counts(user_id, guild_id, moderator_id)


def remove_one_warning(user_id: int, guild_id: int) -> bool:
    removed = _delete_oldest_warnings(user_id, guild_id, 1)
    return removed > 0


def add_strike(user_id: int, guild_id: int, moderator_id: int, reason: str):
    created = datetime.utcnow()
    expire_at = created + timedelta(days=90)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO strikes (user_id, guild_id, moderator_id, reason, created_at, expire_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, guild_id, moderator_id, reason, created.timestamp(), expire_at.timestamp()),
    )
    conn.commit()
    conn.close()


def remove_one_strike(user_id: int, guild_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM strikes WHERE user_id = ? AND guild_id = ? ORDER BY created_at ASC LIMIT 1",
        (user_id, guild_id),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False
    cursor.execute("DELETE FROM strikes WHERE id = ?", (row[0],))
    conn.commit()
    conn.close()
    return True


def add_praise(user_id: int, guild_id: int, moderator_id: int, reason: str):
    created = datetime.utcnow()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO praises (user_id, guild_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, guild_id, moderator_id, reason, created.timestamp()),
    )
    conn.commit()
    conn.close()
    # Normalize: for every 3 praises, remove 1 warning if exists
    normalize_counts(user_id, guild_id, moderator_id)


def normalize_counts(user_id: int, guild_id: int, moderator_id: int):
    # Convert 3 warnings to 1 strike
    while count_warnings(user_id, guild_id) >= 3:
        deleted = _delete_oldest_warnings(user_id, guild_id, 3)
        if deleted < 3:
            break
        add_strike(user_id, guild_id, moderator_id, reason="Авто: 3 предупреждения = страйк")

    # Convert 3 praises to removing 1 warning
    while count_praises(user_id, guild_id) >= 3 and count_warnings(user_id, guild_id) > 0:
        removed = _delete_oldest_praises(user_id, guild_id, 3)
        if removed < 3:
            break
        remove_one_warning(user_id, guild_id)


def get_history(user_id: int, guild_id: int, limit: int = 5, offset: int = 0):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT CASE WHEN type='text' THEN 'Текстовый мут' WHEN type='voice' THEN 'Голосовой мут' ELSE 'Бан' END as type,
            moderator_id, reason, date as created_at, NULL as expire_at FROM punishments_history 
        WHERE user_id = ? AND guild_id = ?
        UNION ALL
        SELECT 'Предупреждение' AS type, moderator_id, reason, created_at, expire_at
        FROM warnings WHERE user_id = ? AND guild_id = ?
        UNION ALL
        SELECT 'Страйк' AS type, moderator_id, reason, created_at, expire_at
        FROM strikes WHERE user_id = ? AND guild_id = ?
        UNION ALL
        SELECT 'Похвала' AS type, moderator_id, reason, created_at, NULL as expire_at
        FROM praises WHERE user_id = ? AND guild_id = ?
        ORDER BY created_at DESC, date DESC
        LIMIT ? OFFSET ?
        """,
        (user_id, guild_id, user_id, guild_id, user_id, guild_id, user_id, guild_id, limit, offset),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def add_punishment_history(user_id: int, guild_id: int, moderator_id: int, ptype: str, reason: str, when_ts: float | None = None):
    """Insert a punishment record (text mute, voice mute, ban) into discipline DB."""
    when_ts = when_ts or datetime.utcnow().timestamp()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO punishments_history (user_id, guild_id, moderator_id, type, reason, date) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, guild_id, moderator_id, ptype, reason, when_ts),
    )
    conn.commit()
    conn.close()


