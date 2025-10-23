# src/database/tickets.py
import sqlite3
import os
from typing import Optional, Dict, Any

class TicketDatabase:
    def __init__(self, db_path: str = "src/database/tickets.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Инициализация базы данных"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Создаем таблицу для хранения счетчика обращений
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ticket_counter (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    current_number INTEGER DEFAULT 0
                )
            ''')
            
            # Создаем таблицу для хранения информации об обращениях
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_number TEXT UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    ticket_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    position TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'open'
                )
            ''')
            
            # Инициализируем счетчик, если его нет
            cursor.execute('SELECT COUNT(*) FROM ticket_counter')
            if cursor.fetchone()[0] == 0:
                cursor.execute('INSERT INTO ticket_counter (current_number) VALUES (0)')
            
            conn.commit()

    def get_next_ticket_number(self) -> str:
        """Получает следующий номер обращения"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Получаем текущий номер
            cursor.execute('SELECT current_number FROM ticket_counter WHERE id = 1')
            result = cursor.fetchone()
            
            if result:
                current_number = result[0]
                next_number = current_number + 1
                
                # Обновляем счетчик
                cursor.execute('UPDATE ticket_counter SET current_number = ? WHERE id = 1', (next_number,))
                conn.commit()
                
                return f"TICKET-{next_number:04d}"
            else:
                # Если записи нет, создаем новую
                cursor.execute('INSERT INTO ticket_counter (current_number) VALUES (1)')
                conn.commit()
                return "TICKET-0001"

    def create_ticket(self, ticket_number: str, user_id: int, ticket_type: str, description: str, position: str = None) -> bool:
        """Создает запись об обращении"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO tickets (ticket_number, user_id, ticket_type, description, position)
                    VALUES (?, ?, ?, ?, ?)
                ''', (ticket_number, user_id, ticket_type, description, position))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False  # Номер уже существует

    def get_ticket_info(self, ticket_number: str) -> Optional[Dict[str, Any]]:
        """Получает информацию об обращении"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT ticket_number, user_id, ticket_type, description, position, created_at, status
                FROM tickets WHERE ticket_number = ?
            ''', (ticket_number,))
            
            result = cursor.fetchone()
            if result:
                return {
                    'ticket_number': result[0],
                    'user_id': result[1],
                    'ticket_type': result[2],
                    'description': result[3],
                    'position': result[4],
                    'created_at': result[5],
                    'status': result[6]
                }
            return None

    def close_ticket(self, ticket_number: str) -> bool:
        """Закрывает обращение"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE tickets SET status = ? WHERE ticket_number = ?', ('closed', ticket_number))
            conn.commit()
            return cursor.rowcount > 0

# Глобальный экземпляр базы данных
ticket_db = TicketDatabase()
