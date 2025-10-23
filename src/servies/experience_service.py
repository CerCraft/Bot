"""
Сервис для подсчета опыта пользователей
"""
import sqlite3
from typing import Optional, Dict, Any
from src.database.economy import init_economy_db, get_connection
from src.core.config import settings


class ExperienceService:
    """Сервис для управления опытом пользователей"""
    
    @staticmethod
    def _ensure_db_initialized() -> None:
        """Убеждается, что база данных инициализирована"""
        try:
            init_economy_db()
        except Exception as e:
            print(f"Ошибка при инициализации базы данных: {e}")
    
    @staticmethod
    def _get_xp_per_level() -> Dict[int, int]:
        """
        Получает настройки опыта за уровень из конфига
        
        Returns:
            Словарь {уровень: необходимое_количество_опыта}
        """
        # Получаем настройки из конфига
        xp_config = getattr(settings, 'ECONOMY_XP_PER_LEVEL', {})
        
        # Если конфиг пустой, используем стандартную формулу
        if not xp_config:
            return {level: level * 100 for level in range(1, 101)}  # 100, 200, 300, ...
        
        return xp_config
    
    @staticmethod
    def _get_xp_sources() -> Dict[str, float]:
        """
        Получает настройки источников опыта из конфига
        
        Returns:
            Словарь {источник: количество_опыта}
        """
        # Получаем настройки из конфига
        xp_sources = getattr(settings, 'ECONOMY_XP_SOURCES', {})
        
        # Если конфиг пустой, используем стандартные значения
        if not xp_sources:
            return {
                'message': 0.5,      # За сообщение
                'voice_minute': 0.5,  # За минуту в войсе
            }
        
        return xp_sources
    
    @staticmethod
    def add_xp_from_message(user_id: int, guild_id: int) -> None:
        """
        Добавляет опыт за отправленное сообщение
        
        Args:
            user_id: ID пользователя
            guild_id: ID сервера
        """
        ExperienceService._ensure_db_initialized()
        
        xp_sources = ExperienceService._get_xp_sources()
        xp_amount = xp_sources.get('message', 0.5)
        
        if xp_amount <= 0:
            return
        
        conn = get_connection()
        c = conn.cursor()
        
        try:
            # Добавляем опыт
            c.execute("""
                UPDATE accounts 
                SET xp = xp + ? 
                WHERE user_id=? AND guild_id=?
            """, (xp_amount, user_id, guild_id))
            
            # Проверяем повышение уровня
            ExperienceService._check_level_up(user_id, guild_id, conn, c)
            
            conn.commit()
            
        except Exception as e:
            print(f"Ошибка при добавлении опыта за сообщение: {e}")
        finally:
            conn.close()
    
    @staticmethod
    def add_xp_from_voice(user_id: int, guild_id: int, minutes: float) -> None:
        """
        Добавляет опыт за время в войсе
        
        Args:
            user_id: ID пользователя
            guild_id: ID сервера
            minutes: Количество минут в войсе
        """
        ExperienceService._ensure_db_initialized()
        
        xp_sources = ExperienceService._get_xp_sources()
        xp_per_minute = xp_sources.get('voice_minute', 0.5)
        
        if xp_per_minute <= 0 or minutes <= 0:
            return
        
        xp_amount = minutes * xp_per_minute
        
        conn = get_connection()
        c = conn.cursor()
        
        try:
            # Добавляем опыт
            c.execute("""
                UPDATE accounts 
                SET xp = xp + ? 
                WHERE user_id=? AND guild_id=?
            """, (xp_amount, user_id, guild_id))
            
            # Проверяем повышение уровня
            ExperienceService._check_level_up(user_id, guild_id, conn, c)
            
            conn.commit()
            
        except Exception as e:
            print(f"Ошибка при добавлении опыта за войс: {e}")
        finally:
            conn.close()
    
    @staticmethod
    def _check_level_up(user_id: int, guild_id: int, conn: sqlite3.Connection, c) -> None:
        """
        Проверяет и обрабатывает повышение уровня
        
        Args:
            user_id: ID пользователя
            guild_id: ID сервера
            conn: Соединение с БД
            c: Курсор БД
        """
        try:
            # Получаем текущий уровень и опыт
            c.execute("SELECT level, xp FROM accounts WHERE user_id=? AND guild_id=?", (user_id, guild_id))
            result = c.fetchone()
            
            if not result:
                return
            
            current_level, current_xp = result
            xp_per_level = ExperienceService._get_xp_per_level()
            
            # Проверяем, нужно ли повысить уровень
            while current_level in xp_per_level and current_xp >= xp_per_level[current_level]:
                current_level += 1
                current_xp -= xp_per_level[current_level - 1]
            
            # Обновляем уровень и опыт
            c.execute("""
                UPDATE accounts 
                SET level = ?, xp = ? 
                WHERE user_id=? AND guild_id=?
            """, (current_level, current_xp, user_id, guild_id))
            
        except Exception as e:
            print(f"Ошибка при проверке повышения уровня: {e}")
    
    @staticmethod
    def get_user_level_info(user_id: int, guild_id: int) -> Dict[str, Any]:
        """
        Получает информацию об уровне пользователя
        
        Args:
            user_id: ID пользователя
            guild_id: ID сервера
            
        Returns:
            Словарь с информацией об уровне
        """
        ExperienceService._ensure_db_initialized()
        
        conn = get_connection()
        c = conn.cursor()
        
        try:
            c.execute("SELECT level, xp FROM accounts WHERE user_id=? AND guild_id=?", (user_id, guild_id))
            result = c.fetchone()
            
            if not result:
                return {
                    'level': 1,
                    'xp': 0,
                    'xp_to_next': 100,
                    'xp_progress': 0.0
                }
            
            level, xp = result
            xp_per_level = ExperienceService._get_xp_per_level()
            
            # Получаем необходимый опыт для следующего уровня
            next_level = level + 1
            xp_needed = xp_per_level.get(next_level, next_level * 100)
            
            # Прогресс до следующего уровня
            progress = (xp / xp_needed) * 100 if xp_needed > 0 else 0
            
            return {
                'level': level,
                'xp': xp,
                'xp_to_next': xp_needed,
                'xp_progress': round(progress, 1)
            }
            
        except Exception as e:
            print(f"Ошибка при получении информации об уровне: {e}")
            return {
                'level': 1,
                'xp': 0,
                'xp_to_next': 100,
                'xp_progress': 0.0
            }
        finally:
            conn.close()
    
    @staticmethod
    def get_top_by_level(guild_id: int, limit: int = 10) -> list:
        """
        Получает топ пользователей по уровню
        
        Args:
            guild_id: ID сервера
            limit: Количество записей в топе
            
        Returns:
            Список кортежей (user_id, level, xp)
        """
        ExperienceService._ensure_db_initialized()
        
        conn = get_connection()
        c = conn.cursor()
        
        try:
            c.execute("""
                SELECT user_id, level, xp 
                FROM accounts 
                WHERE guild_id=? 
                ORDER BY level DESC, xp DESC 
                LIMIT ?
            """, (guild_id, limit))
            return c.fetchall()
            
        except Exception as e:
            print(f"Ошибка при получении топа по уровню: {e}")
            return []
        finally:
            conn.close()
    
    @staticmethod
    def get_rank_by_level(user_id: int, guild_id: int) -> int:
        """
        Получает позицию пользователя в топе по уровню
        
        Args:
            user_id: ID пользователя
            guild_id: ID сервера
            
        Returns:
            Позиция в топе (начиная с 1)
        """
        ExperienceService._ensure_db_initialized()
        
        conn = get_connection()
        c = conn.cursor()
        
        try:
            c.execute("""
                SELECT COUNT(*) + 1 
                FROM accounts a 
                WHERE a.guild_id = ? 
                AND (a.level > (
                    SELECT level FROM accounts 
                    WHERE user_id=? AND guild_id=?
                ) OR (a.level = (
                    SELECT level FROM accounts 
                    WHERE user_id=? AND guild_id=?
                ) AND a.xp > (
                    SELECT xp FROM accounts 
                    WHERE user_id=? AND guild_id=?
                )))
            """, (guild_id, user_id, guild_id, user_id, guild_id, user_id, guild_id))
            
            result = c.fetchone()
            return int(result[0]) if result else 1
            
        except Exception as e:
            print(f"Ошибка при получении ранга по уровню: {e}")
            return 1
        finally:
            conn.close()
    
    @staticmethod
    def reset_user_xp(user_id: int, guild_id: int) -> bool:
        """
        Сбрасывает опыт пользователя
        
        Args:
            user_id: ID пользователя
            guild_id: ID сервера
            
        Returns:
            True если успешно, False если ошибка
        """
        ExperienceService._ensure_db_initialized()
        
        conn = get_connection()
        c = conn.cursor()
        
        try:
            c.execute("""
                UPDATE accounts 
                SET level = 1, xp = 0 
                WHERE user_id=? AND guild_id=?
            """, (user_id, guild_id))
            conn.commit()
            return c.rowcount > 0
            
        except Exception as e:
            print(f"Ошибка при сбросе опыта: {e}")
            return False
        finally:
            conn.close()
    
    @staticmethod
    def check_all_users_level_up(guild_id: int) -> int:
        """
        Проверяет всех пользователей сервера на повышение уровня
        
        Args:
            guild_id: ID сервера
            
        Returns:
            Количество пользователей, у которых повысился уровень
        """
        ExperienceService._ensure_db_initialized()
        
        conn = get_connection()
        c = conn.cursor()
        
        level_ups = 0
        
        try:
            # Получаем всех пользователей сервера
            c.execute("""
                SELECT user_id, level, xp 
                FROM accounts 
                WHERE guild_id=?
            """, (guild_id,))
            
            users = c.fetchall()
            xp_per_level = ExperienceService._get_xp_per_level()
            
            for user_id, current_level, current_xp in users:
                new_level = current_level
                remaining_xp = current_xp
                
                # Проверяем, нужно ли повысить уровень
                while new_level in xp_per_level and remaining_xp >= xp_per_level[new_level]:
                    remaining_xp -= xp_per_level[new_level]
                    new_level += 1
                
                # Если уровень изменился, обновляем в БД
                if new_level != current_level:
                    c.execute("""
                        UPDATE accounts 
                        SET level = ?, xp = ? 
                        WHERE user_id=? AND guild_id=?
                    """, (new_level, remaining_xp, user_id, guild_id))
                    level_ups += 1
            
            conn.commit()
            
        except Exception as e:
            print(f"Ошибка при проверке повышения уровня для всех пользователей: {e}")
        finally:
            conn.close()
        
        return level_ups
    
    @staticmethod
    def check_user_level_up(user_id: int, guild_id: int) -> bool:
        """
        Проверяет конкретного пользователя на повышение уровня
        
        Args:
            user_id: ID пользователя
            guild_id: ID сервера
            
        Returns:
            True если уровень повысился, False если нет
        """
        ExperienceService._ensure_db_initialized()
        
        conn = get_connection()
        c = conn.cursor()
        
        level_increased = False
        
        try:
            # Получаем текущий уровень и опыт пользователя
            c.execute("""
                SELECT level, xp 
                FROM accounts 
                WHERE user_id=? AND guild_id=?
            """, (user_id, guild_id))
            
            result = c.fetchone()
            if not result:
                return False
            
            current_level, current_xp = result
            xp_per_level = ExperienceService._get_xp_per_level()
            
            new_level = current_level
            remaining_xp = current_xp
            
            # Проверяем, нужно ли повысить уровень
            while new_level in xp_per_level and remaining_xp >= xp_per_level[new_level]:
                remaining_xp -= xp_per_level[new_level]
                new_level += 1
            
            # Если уровень изменился, обновляем в БД
            if new_level != current_level:
                c.execute("""
                    UPDATE accounts 
                    SET level = ?, xp = ? 
                    WHERE user_id=? AND guild_id=?
                """, (new_level, remaining_xp, user_id, guild_id))
                conn.commit()
                level_increased = True
            
        except Exception as e:
            print(f"Ошибка при проверке повышения уровня для пользователя {user_id}: {e}")
        finally:
            conn.close()
        
        return level_increased