"""
Сервис для подсчета отправленных сообщений пользователями
"""
import sqlite3
from typing import Optional
from src.database.economy import init_economy_db, get_connection


class MessageCounterService:
    """Сервис для подсчета и управления статистикой сообщений"""
    
    @staticmethod
    def _ensure_db_initialized() -> None:
        """Убеждается, что база данных инициализирована"""
        try:
            init_economy_db()
        except Exception as e:
            print(f"Ошибка при инициализации базы данных: {e}")
    
    @staticmethod
    def increment_message_count(user_id: int, guild_id: int) -> None:
        """
        Увеличивает счетчик сообщений для пользователя
        
        Args:
            user_id: ID пользователя
            guild_id: ID сервера
        """
        MessageCounterService._ensure_db_initialized()
        conn = get_connection()
        c = conn.cursor()
        
        try:
            # Проверяем, существует ли аккаунт
            c.execute("SELECT user_id FROM accounts WHERE user_id=? AND guild_id=?", (user_id, guild_id))
            if not c.fetchone():
                # Создаем аккаунт если не существует
                c.execute("""
                    INSERT INTO accounts (user_id, guild_id, cash, bank, xp, level, voice_seconds, 
                                        arrest_until, daily_cd, work_cd, weekly_cd, rob_cd, 
                                        robberies_total, robberies_success, robberies_fail, 
                                        robberies_arrest, messages_sent, temp_roles_json)
                    VALUES (?, ?, 0, 0, 0, 1, 0, NULL, NULL, NULL, NULL, NULL, 0, 0, 0, 0, 0, NULL)
                """, (user_id, guild_id))
            
            # Увеличиваем счетчик сообщений
            c.execute("""
                UPDATE accounts 
                SET messages_sent = messages_sent + 1 
                WHERE user_id=? AND guild_id=?
            """, (user_id, guild_id))
            
            conn.commit()
            
        except Exception as e:
            print(f"Ошибка при увеличении счетчика сообщений: {e}")
        finally:
            conn.close()
    
    @staticmethod
    def get_message_count(user_id: int, guild_id: int) -> int:
        """
        Получает количество отправленных сообщений пользователем
        
        Args:
            user_id: ID пользователя
            guild_id: ID сервера
            
        Returns:
            Количество отправленных сообщений
        """
        MessageCounterService._ensure_db_initialized()
        conn = get_connection()
        c = conn.cursor()
        
        try:
            c.execute("SELECT messages_sent FROM accounts WHERE user_id=? AND guild_id=?", (user_id, guild_id))
            result = c.fetchone()
            return result[0] if result else 0
            
        except Exception as e:
            print(f"Ошибка при получении счетчика сообщений: {e}")
            return 0
        finally:
            conn.close()
    
    @staticmethod
    def get_top_by_messages(guild_id: int, limit: int = 10) -> list:
        """
        Получает топ пользователей по количеству сообщений
        
        Args:
            guild_id: ID сервера
            limit: Количество записей в топе
            
        Returns:
            Список кортежей (user_id, messages_sent)
        """
        MessageCounterService._ensure_db_initialized()
        conn = get_connection()
        c = conn.cursor()
        
        try:
            c.execute("""
                SELECT user_id, messages_sent 
                FROM accounts 
                WHERE guild_id=? AND messages_sent > 0
                ORDER BY messages_sent DESC 
                LIMIT ?
            """, (guild_id, limit))
            return c.fetchall()
            
        except Exception as e:
            print(f"Ошибка при получении топа по сообщениям: {e}")
            return []
        finally:
            conn.close()
    
    @staticmethod
    def get_rank_by_messages(user_id: int, guild_id: int) -> int:
        """
        Получает позицию пользователя в топе по сообщениям
        
        Args:
            user_id: ID пользователя
            guild_id: ID сервера
            
        Returns:
            Позиция в топе (начиная с 1)
        """
        MessageCounterService._ensure_db_initialized()
        conn = get_connection()
        c = conn.cursor()
        
        try:
            c.execute("""
                SELECT COUNT(*) + 1 
                FROM accounts a 
                WHERE a.guild_id = ? AND a.messages_sent > (
                    SELECT COALESCE(messages_sent, 0) 
                    FROM accounts 
                    WHERE user_id=? AND guild_id=?
                )
            """, (guild_id, user_id, guild_id))
            result = c.fetchone()
            return int(result[0]) if result else 1
            
        except Exception as e:
            print(f"Ошибка при получении ранга по сообщениям: {e}")
            return 1
        finally:
            conn.close()
    
    @staticmethod
    def reset_message_count(user_id: int, guild_id: int) -> bool:
        """
        Сбрасывает счетчик сообщений для пользователя
        
        Args:
            user_id: ID пользователя
            guild_id: ID сервера
            
        Returns:
            True если успешно, False если ошибка
        """
        MessageCounterService._ensure_db_initialized()
        conn = get_connection()
        c = conn.cursor()
        
        try:
            c.execute("""
                UPDATE accounts 
                SET messages_sent = 0 
                WHERE user_id=? AND guild_id=?
            """, (user_id, guild_id))
            conn.commit()
            return c.rowcount > 0
            
        except Exception as e:
            print(f"Ошибка при сбросе счетчика сообщений: {e}")
            return False
        finally:
            conn.close()
    
    @staticmethod
    def get_guild_stats(guild_id: int) -> dict:
        """
        Получает общую статистику сообщений по серверу
        
        Args:
            guild_id: ID сервера
            
        Returns:
            Словарь со статистикой
        """
        MessageCounterService._ensure_db_initialized()
        conn = get_connection()
        c = conn.cursor()
        
        try:
            # Общее количество сообщений
            c.execute("SELECT SUM(messages_sent) FROM accounts WHERE guild_id=?", (guild_id,))
            total_messages = c.fetchone()[0] or 0
            
            # Количество активных пользователей
            c.execute("SELECT COUNT(*) FROM accounts WHERE guild_id=? AND messages_sent > 0", (guild_id,))
            active_users = c.fetchone()[0] or 0
            
            # Среднее количество сообщений на пользователя
            avg_messages = total_messages / active_users if active_users > 0 else 0
            
            return {
                'total_messages': total_messages,
                'active_users': active_users,
                'avg_messages_per_user': round(avg_messages, 2)
            }
            
        except Exception as e:
            print(f"Ошибка при получении статистики сервера: {e}")
            return {
                'total_messages': 0,
                'active_users': 0,
                'avg_messages_per_user': 0
            }
        finally:
            conn.close()
