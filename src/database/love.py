# src/database/love.py
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from src.database.connection import get_connection

def init_love_db():
    """Инициализация базы данных для love системы"""
    conn = get_connection()
    cursor = conn.cursor()

    # Таблица для пар
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS couples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user1_id INTEGER NOT NULL,
            user2_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            description TEXT DEFAULT '💕 Любовь - это когда два сердца бьются в унисон 💕',
            UNIQUE(user1_id, user2_id)
        )
    """)

    # Таблица для отслеживания времени в голосовых комнатах
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS voice_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            couple_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP NULL,
            duration_seconds INTEGER DEFAULT 0,
            user1_present BOOLEAN DEFAULT FALSE,
            user2_present BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (couple_id) REFERENCES couples (id)
        )
    """)

    # Таблица для активных сессий
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            couple_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user1_present BOOLEAN DEFAULT FALSE,
            user2_present BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (couple_id) REFERENCES couples (id)
        )
    """)

    # Таблица для доступа к love комнатам
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS love_room_access (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Обновляем существующие таблицы, добавляя новые колонки если их нет
    try:
        # Проверяем и добавляем колонки в voice_sessions
        cursor.execute("PRAGMA table_info(voice_sessions)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'user1_present' not in columns:
            cursor.execute("ALTER TABLE voice_sessions ADD COLUMN user1_present BOOLEAN DEFAULT FALSE")
        if 'user2_present' not in columns:
            cursor.execute("ALTER TABLE voice_sessions ADD COLUMN user2_present BOOLEAN DEFAULT FALSE")
        
        # Проверяем и добавляем колонки в active_sessions
        cursor.execute("PRAGMA table_info(active_sessions)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'user1_present' not in columns:
            cursor.execute("ALTER TABLE active_sessions ADD COLUMN user1_present BOOLEAN DEFAULT FALSE")
        if 'user2_present' not in columns:
            cursor.execute("ALTER TABLE active_sessions ADD COLUMN user2_present BOOLEAN DEFAULT FALSE")
            
    except Exception as e:
        logging.warning(f"Предупреждение при обновлении схемы: {e}")

    conn.commit()
    conn.close()
    logging.info("💕 Love база данных инициализирована")


def create_couple(user1_id: int, user2_id: int, description: str = None) -> bool:
    """Создать пару"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Проверяем, что пользователи не состоят уже в паре
        cursor.execute("""
            SELECT id FROM couples 
            WHERE user1_id = ? OR user2_id = ? OR user1_id = ? OR user2_id = ?
        """, (user1_id, user1_id, user2_id, user2_id))
        
        if cursor.fetchone():
            return False
        
        # Создаем пару
        cursor.execute("""
            INSERT INTO couples (user1_id, user2_id, description)
            VALUES (?, ?, ?)
        """, (user1_id, user2_id, description or '💕 Любовь - это когда два сердца бьются в унисон 💕'))
        
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Ошибка при создании пары: {e}")
        return False
    finally:
        conn.close()

def get_couple_by_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Получить пару по ID пользователя"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT * FROM couples 
            WHERE user1_id = ? OR user2_id = ?
        """, (user_id, user_id))
        
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()

def get_couple_by_id(couple_id: int) -> Optional[Dict[str, Any]]:
    """Получить пару по ID пары"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM couples WHERE id = ?", (couple_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()

def update_couple_description(couple_id: int, description: str) -> bool:
    """Обновить описание пары"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE couples SET description = ? WHERE id = ?
        """, (description, couple_id))
        
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"Ошибка при обновлении описания пары: {e}")
        return False
    finally:
        conn.close()

def delete_couple(couple_id: int) -> bool:
    """Удалить пару"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Удаляем активные сессии
        cursor.execute("DELETE FROM active_sessions WHERE couple_id = ?", (couple_id,))
        
        # Удаляем историю сессий
        cursor.execute("DELETE FROM voice_sessions WHERE couple_id = ?", (couple_id,))
        
        # Удаляем пару
        cursor.execute("DELETE FROM couples WHERE id = ?", (couple_id,))
        
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"Ошибка при удалении пары: {e}")
        return False
    finally:
        conn.close()

def start_voice_session(couple_id: int, channel_id: int) -> bool:
    """Начать сессию в голосовом канале"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Проверяем, есть ли уже активная сессия
        cursor.execute("""
            SELECT id FROM active_sessions WHERE couple_id = ?
        """, (couple_id,))
        
        if cursor.fetchone():
            return False
        
        # Создаем новую активную сессию
        cursor.execute("""
            INSERT INTO active_sessions (couple_id, channel_id, started_at)
            VALUES (?, ?, ?)
        """, (couple_id, channel_id, datetime.utcnow().isoformat()))
        
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Ошибка при начале сессии: {e}")
        return False
    finally:
        conn.close()

def end_voice_session(couple_id: int) -> Optional[int]:
    """Завершить сессию в голосовом канале и вернуть продолжительность в секундах"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Получаем активную сессию
        cursor.execute("""
            SELECT * FROM active_sessions WHERE couple_id = ?
        """, (couple_id,))
        
        session = cursor.fetchone()
        if not session:
            logging.info(f"Нет активной сессии для пары {couple_id}")
            return None
        
        # Вычисляем продолжительность
        started_at = datetime.fromisoformat(session['started_at'])
        ended_at = datetime.utcnow()  # Используем UTC время
        duration = int((ended_at - started_at).total_seconds())
        
        logging.info(f"Сессия пары {couple_id}: начата {started_at}, завершена {ended_at}, продолжительность {duration} секунд")
        
        # Сохраняем в историю только если продолжительность больше 0
        if duration > 0:
            cursor.execute("""
                INSERT INTO voice_sessions (couple_id, channel_id, started_at, ended_at, duration_seconds)
                VALUES (?, ?, ?, ?, ?)
            """, (session['couple_id'], session['channel_id'], session['started_at'], 
                  ended_at.isoformat(), duration))
            logging.info(f"Сохранена сессия пары {couple_id} с продолжительностью {duration} секунд")
        else:
            logging.info(f"Сессия пары {couple_id} слишком короткая ({duration} секунд), не сохраняем")
        
        # Удаляем активную сессию
        cursor.execute("DELETE FROM active_sessions WHERE id = ?", (session['id'],))
        
        conn.commit()
        return duration
    except Exception as e:
        logging.error(f"Ошибка при завершении сессии: {e}")
        return None
    finally:
        conn.close()

def get_total_voice_time(couple_id: int) -> int:
    """Получить общее время проведенное в голосовых каналах (в секундах)"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT COALESCE(SUM(duration_seconds), 0) as total_time
            FROM voice_sessions WHERE couple_id = ?
        """, (couple_id,))
        
        result = cursor.fetchone()
        return result['total_time'] if result else 0
    finally:
        conn.close()

def get_active_session(couple_id: int) -> Optional[Dict[str, Any]]:
    """Получить активную сессию пары"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT * FROM active_sessions WHERE couple_id = ?
        """, (couple_id,))
        
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()

def cleanup_expired_sessions():
    """Очистка устаревших активных сессий (если канал был удален)"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Удаляем сессии старше 24 часов
        cursor.execute("""
            DELETE FROM active_sessions 
            WHERE started_at < datetime('now', '-24 hours')
        """)
        
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        logging.error(f"Ошибка при очистке сессий: {e}")
        return 0
    finally:
        conn.close()

def has_love_room_access(user_id: int) -> bool:
    """Проверить, есть ли у пользователя доступ к love комнатам"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT expires_at FROM love_room_access 
            WHERE user_id = ? AND expires_at > datetime('now')
        """, (user_id,))
        
        result = cursor.fetchone()
        return result is not None
    finally:
        conn.close()

def get_love_room_access_expiry(user_id: int) -> Optional[str]:
    """Получить дату истечения доступа к love комнатам"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT expires_at FROM love_room_access 
            WHERE user_id = ? AND expires_at > datetime('now')
        """, (user_id,))
        
        result = cursor.fetchone()
        return result['expires_at'] if result else None
    finally:
        conn.close()

def add_love_room_access(user_id: int, months: int = 1) -> bool:
    """Добавить доступ к love комнатам на указанное количество месяцев"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Проверяем, есть ли уже активный доступ
        cursor.execute("""
            SELECT expires_at FROM love_room_access 
            WHERE user_id = ? AND expires_at > datetime('now')
        """, (user_id,))
        
        existing = cursor.fetchone()
        
        if existing:
            # Продлеваем существующий доступ
            current_expiry = datetime.fromisoformat(existing['expires_at'])
            new_expiry = current_expiry + timedelta(days=30 * months)
            
            cursor.execute("""
                UPDATE love_room_access 
                SET expires_at = ? 
                WHERE user_id = ?
            """, (new_expiry.isoformat(), user_id))
        else:
            # Создаем новый доступ
            expires_at = datetime.now() + timedelta(days=30 * months)
            
            cursor.execute("""
                INSERT INTO love_room_access (user_id, expires_at)
                VALUES (?, ?)
            """, (user_id, expires_at.isoformat()))
        
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Ошибка при добавлении доступа к love комнатам: {e}")
        return False
    finally:
        conn.close()

def remove_expired_access():
    """Удалить истекшие доступы к love комнатам"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM love_room_access 
            WHERE expires_at <= datetime('now')
        """)
        
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        logging.error(f"Ошибка при удалении истекших доступов: {e}")
        return 0
    finally:
        conn.close()
