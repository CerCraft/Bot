# src/database/clans.py
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from src.database.connection import get_connection

def _build_clan_dict(data: Dict) -> Dict:
    """Преобразование строки БД в словарь клана"""
    return {
        'id': data.get('id'),
        'name': data.get('name'),
        'description': data.get('description'),
        'color': data.get('color'),
        'avatar_url': data.get('avatar_url'),
        'emoji': data.get('emoji', '🛡️'),
        'owner_id': data.get('owner_id'),
        'role_id': data.get('role_id'),
        'text_channel_id': data.get('text_channel_id'),
        'voice_channel_id': data.get('voice_channel_id'),
        'max_members': data.get('max_members'),
        'voice_channels_count': data.get('voice_channels_count'),
        'created_at': data.get('created_at'),
        'last_payment': data.get('last_payment'),
        'is_active': data.get('is_active', True)
    }


def init_clans_db():
    """Инициализация таблиц для системы кланов"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Таблица кланов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            color INTEGER,
            avatar_url TEXT,
            owner_id INTEGER NOT NULL,
            role_id INTEGER,
            text_channel_id INTEGER,
            voice_channel_id INTEGER,
            max_members INTEGER DEFAULT 20,
            voice_channels_count INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_payment TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        )
    """)
    
    # Миграция: добавляем поле avatar_url если его нет
    try:
        cursor.execute("ALTER TABLE clans ADD COLUMN avatar_url TEXT")
        logging.info("Добавлено поле avatar_url в таблицу clans")
    except sqlite3.OperationalError:
        # Поле уже существует
        pass
    
    # Миграция: добавляем поле emoji если его нет
    try:
        cursor.execute("ALTER TABLE clans ADD COLUMN emoji TEXT DEFAULT '🛡️'")
        logging.info("Добавлено поле emoji в таблицу clans")
    except sqlite3.OperationalError:
        # Поле уже существует
        pass
    
    # Таблица участников кланов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clan_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clan_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT DEFAULT 'member',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (clan_id) REFERENCES clans (id) ON DELETE CASCADE,
            UNIQUE(clan_id, user_id)
        )
    """)
    
    # Таблица голосовых каналов кланов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clan_voice_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clan_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (clan_id) REFERENCES clans (id) ON DELETE CASCADE
        )
    """)
    
    conn.commit()
    conn.close()
    logging.info("📦 База данных кланов инициализирована")

def create_clan(name: str, description: str, color: int, owner_id: int, role_id: int,
                text_channel_id: int, voice_channel_id: int, avatar_url: str = None, emoji: str = '🛡️') -> int:
    """Создание нового клана"""
    conn = get_connection()
    cursor = conn.cursor()
    
    logging.info(f"Создаем клан в БД:")
    logging.info(f"- Название: {name}")
    logging.info(f"- Роль ID: {role_id}")
    logging.info(f"- Текстовый канал ID: {text_channel_id}")
    logging.info(f"- Голосовой канал ID: {voice_channel_id}")
    logging.info(f"- Эмодзи: {emoji}")
    
    cursor.execute("""
        INSERT INTO clans (name, description, color, avatar_url, emoji, owner_id, role_id, text_channel_id, voice_channel_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, description, color, avatar_url, emoji, owner_id, role_id, text_channel_id, voice_channel_id))

    clan_id = cursor.lastrowid

    # Добавляем владельца как участника с ролью owner
    cursor.execute("""
        INSERT INTO clan_members (clan_id, user_id, role)
        VALUES (?, ?, 'owner')
    """, (clan_id, owner_id))

    # Добавляем голосовой канал
    cursor.execute("""
        INSERT INTO clan_voice_channels (clan_id, channel_id)
        VALUES (?, ?)
    """, (clan_id, voice_channel_id))

    conn.commit()
    conn.close()

    logging.info(f"🏰 Создан клан '{name}' (ID: {clan_id}) владельцем {owner_id}")
    return clan_id

def get_clan_by_id(clan_id: int) -> Optional[Dict]:
    """Получение информации о клане по ID"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM clans WHERE id = ? AND is_active = TRUE
    """, (clan_id,))
    
    result = cursor.fetchone()
    conn.close()

    if result:
        data = dict(result)
        logging.info(f"Читаем клан из БД (ID: {clan_id}):")
        logging.info(f"- Роль ID: {data.get('role_id')}")
        logging.info(f"- Текстовый канал ID: {data.get('text_channel_id')}")
        logging.info(f"- Голосовой канал ID: {data.get('voice_channel_id')}")
        logging.info(f"- Эмодзи: {data.get('emoji', '🛡️')}")
        data.setdefault('avatar_url', None)
        data.setdefault('emoji', '🛡️')
        return _build_clan_dict(data)
    return None

def get_clan_by_name(name: str, include_inactive: bool = False) -> Optional[Dict]:
    """Получение информации о клане по имени"""
    conn = get_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM clans WHERE name = ?"
    params = [name]
    
    if not include_inactive:
        query += " AND is_active = TRUE"
    
    cursor.execute(query, params)
    
    result = cursor.fetchone()
    conn.close()

    if result:
        data = dict(result)
        data.setdefault('avatar_url', None)
        data.setdefault('emoji', '🛡️')
        return _build_clan_dict(data)
    return None

def get_user_clan(user_id: int) -> Optional[Dict]:
    """Получение клана пользователя"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT c.* FROM clans c
        JOIN clan_members cm ON c.id = cm.clan_id
        WHERE cm.user_id = ? AND c.is_active = TRUE
    """, (user_id,))
    
    result = cursor.fetchone()
    conn.close()

    if result:
        data = dict(result)
        data.setdefault('avatar_url', None)
        data.setdefault('emoji', '🛡️')
        return _build_clan_dict(data)
    return None

def get_clan_members(clan_id: int) -> List[Dict]:
    """Получение списка участников клана"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT user_id, role, joined_at FROM clan_members
        WHERE clan_id = ?
        ORDER BY joined_at ASC
    """, (clan_id,))
    
    results = cursor.fetchall()
    conn.close()

    members = []
    for row in results:
        data = dict(row)
        members.append({
            'user_id': data.get('user_id'),
            'role': data.get('role'),
            'joined_at': data.get('joined_at')
        })
    return members

def add_clan_member(clan_id: int, user_id: int, role: str = 'member') -> bool:
    """Добавление участника в клан"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO clan_members (clan_id, user_id, role)
            VALUES (?, ?, ?)
        """, (clan_id, user_id, role))
        
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def remove_clan_member(clan_id: int, user_id: int) -> bool:
    """Удаление участника из клана"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        DELETE FROM clan_members WHERE clan_id = ? AND user_id = ?
    """, (clan_id, user_id))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return affected > 0

def update_clan_member_role(clan_id: int, user_id: int, role: str) -> bool:
    """Обновление роли участника клана"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE clan_members SET role = ? WHERE clan_id = ? AND user_id = ?
    """, (role, clan_id, user_id))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return affected > 0

def get_clan_member_role(clan_id: int, user_id: int) -> Optional[str]:
    """Получение роли участника клана"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT role FROM clan_members WHERE clan_id = ? AND user_id = ?
    """, (clan_id, user_id))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return dict(result).get('role')
    return None

def update_clan_info(clan_id: int, name: str = None, description: str = None, color: int = None, avatar_url: str = None, emoji: str = None) -> bool:
    """Обновление информации о клане"""
    conn = get_connection()
    cursor = conn.cursor()
    
    updates = []
    params = []
    
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    
    if color is not None:
        updates.append("color = ?")
        params.append(color)
    
    if avatar_url is not None:
        updates.append("avatar_url = ?")
        params.append(avatar_url)
    
    if emoji is not None:
        updates.append("emoji = ?")
        params.append(emoji)
    
    if not updates:
        conn.close()
        return False
    
    params.append(clan_id)
    
    cursor.execute(f"""
        UPDATE clans SET {', '.join(updates)}
        WHERE id = ?
    """, params)
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return affected > 0

def update_clan_max_members(clan_id: int, max_members: int) -> bool:
    """Обновление максимального количества участников"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE clans SET max_members = ? WHERE id = ?
    """, (max_members, clan_id))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return affected > 0

def add_clan_voice_channel(clan_id: int, channel_id: int) -> bool:
    """Добавление голосового канала клана"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO clan_voice_channels (clan_id, channel_id)
            VALUES (?, ?)
        """, (clan_id, channel_id))
        
        # Обновляем счетчик голосовых каналов
        cursor.execute("""
            UPDATE clans SET voice_channels_count = voice_channels_count + 1
            WHERE id = ?
        """, (clan_id,))
        
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def get_clan_voice_channels(clan_id: int) -> List[int]:
    """Получение списка голосовых каналов клана"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT channel_id FROM clan_voice_channels WHERE clan_id = ?
    """, (clan_id,))
    
    results = cursor.fetchall()
    conn.close()

    return [dict(row).get('channel_id') for row in results]

def get_all_clans() -> List[Dict]:
    """Получение списка всех активных кланов"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM clans WHERE is_active = TRUE ORDER BY created_at ASC
    """)
    
    results = cursor.fetchall()
    conn.close()

    clans = []
    for row in results:
        data = dict(row)
        data.setdefault('avatar_url', None)
        data.setdefault('emoji', '🛡️')
        clans.append(_build_clan_dict(data))
    return clans

def update_clan_payment(clan_id: int) -> bool:
    """Обновление времени последней оплаты"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE clans SET last_payment = CURRENT_TIMESTAMP WHERE id = ?
    """, (clan_id,))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return affected > 0

def deactivate_clan(clan_id: int) -> bool:
    """Деактивация клана"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE clans SET is_active = FALSE WHERE id = ?
    """, (clan_id,))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    return affected > 0

def get_clans_for_payment() -> List[Dict]:
    """Получение кланов, которым нужно списать оплату"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Получаем кланы, у которых последняя оплата была более месяца назад
    cursor.execute("""
        SELECT * FROM clans 
        WHERE is_active = TRUE 
        AND datetime(last_payment, '+1 month') <= datetime('now')
        ORDER BY last_payment ASC
    """)
    
    results = cursor.fetchall()
    conn.close()

    clans = []
    for row in results:
        data = dict(row)
        data.setdefault('avatar_url', None)
        data.setdefault('emoji', '🛡️')
        clans.append(_build_clan_dict(data))
    return clans

def get_top_clans_by_members(limit: int = 10) -> List[Tuple[int, str, int]]:
    """Получение топа кланов по количеству участников"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT c.id, c.name, COUNT(cm.user_id) as member_count
        FROM clans c
        LEFT JOIN clan_members cm ON c.id = cm.clan_id
        WHERE c.is_active = TRUE
        GROUP BY c.id, c.name
        ORDER BY member_count DESC, c.created_at ASC
        LIMIT ?
    """, (limit,))
    
    results = cursor.fetchall()
    conn.close()
    
    return [(row['id'], row['name'], row['member_count']) for row in results]
