# src/cogs/love.py
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import asyncio
import logging
from typing import Optional

from src.core.config import settings
from src.utils.embed import create_embed, EmbedColors
from src.database.love import (
    init_love_db,
    create_couple,
    get_couple_by_user,
    get_couple_by_id,
    update_couple_description,
    delete_couple,
    start_voice_session,
    end_voice_session,
    get_total_voice_time,
    get_active_session,
    cleanup_expired_sessions,
    has_love_room_access,
    get_love_room_access_expiry,
    add_love_room_access,
    remove_expired_access,
)
from src.database.economy import (
    get_or_create_account,
    add_cash,
    transfer_cash_to_bank
)
from src.database.connection import get_connection

class MarryConfirmationView(discord.ui.View):
    def __init__(self, proposer: discord.Member, target: discord.Member, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.proposer = proposer
        self.target = target
        self.confirmed = False
    
    @discord.ui.button(label="Принять", style=discord.ButtonStyle.success, emoji="💕")
    async def accept_marriage(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("❌ Только приглашенный пользователь может принять предложение!", ephemeral=True)
            return
        
        # Проверяем баланс инициатора
        proposer_account = get_or_create_account(self.proposer.id, settings.TEST_GUILD_ID)
        marry_cost = settings.LOVE_MARRY_COST
        
        if proposer_account[0] < marry_cost:  # cash - первый элемент tuple
            embed = create_embed(
                title="❌ Недостаточно средств",
                description=f"У {self.proposer.display_name} недостаточно средств для создания пары.\n"
                           f"Требуется: {marry_cost} {settings.ECONOMY_SYMBOL}",
                color=EmbedColors.ERROR,
                author=interaction.user
            )
            await interaction.response.edit_message(embed=embed, view=None)
            return
        
        # Списываем средства
        add_cash(self.proposer.id, settings.TEST_GUILD_ID, -marry_cost)
        
        self.confirmed = True
        self.stop()
        
        # Создаем пару
        success = create_couple(self.proposer.id, self.target.id)
        
        if success:
            embed = create_embed(
                title="💕 Пара создана!",
                description=f"Поздравляем! {self.proposer.display_name} и {self.target.display_name} теперь пара!\n"
                           f"Стоимость создания пары: {marry_cost} {settings.ECONOMY_SYMBOL}",
                color=EmbedColors.SUCCESS,
                author=interaction.user
            )
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            # Возвращаем деньги при ошибке
            add_cash(self.proposer.id, settings.TEST_GUILD_ID, marry_cost)
            embed = create_embed(
                title="❌ Ошибка",
                description="Не удалось создать пару. Деньги возвращены.",
                color=EmbedColors.ERROR,
                author=interaction.user
            )
            await interaction.response.edit_message(embed=embed, view=None)
    
    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger, emoji="❌")
    async def decline_marriage(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("❌ Только приглашенный пользователь может отклонить предложение!", ephemeral=True)
            return
        
        self.stop()
        
        embed = create_embed(
            title="💔 Предложение отклонено",
            description=f"{self.target.display_name} отклонил предложение о создании пары.",
            color=EmbedColors.WARNING,
            author=interaction.user
        )
        await interaction.response.edit_message(embed=embed, view=None)
    
    async def on_timeout(self):
        # Если время истекло, отправляем сообщение об отмене
        embed = create_embed(
            title="⏰ Время истекло",
            description=f"Предложение о создании пары с {self.target.display_name} было отменено из-за истечения времени.",
            color=EmbedColors.WARNING,
            author=self.proposer
        )
        
        # Находим сообщение и обновляем его
        for item in self.children:
            item.disabled = True
        
        try:
            # Пытаемся найти сообщение и обновить его
            # Это может не сработать, если сообщение уже было удалено
            pass
        except:
            pass

class LoveRoomAccessView(discord.ui.View):
    def __init__(self, user: discord.Member, bot, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.user = user
        self.bot = bot
    
    def format_time(self, seconds: int) -> str:
        """Форматирование времени в часы:минуты:секунды"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours} часов {minutes} минут {secs} секунд"
    
    def get_days_together(self, created_at: str) -> int:
        """Получить количество дней вместе"""
        created = datetime.fromisoformat(created_at)
        return (datetime.now() - created).days
    
    @discord.ui.button(label="Купить доступ к Love комнатам", style=discord.ButtonStyle.primary, emoji="💕")
    async def buy_room_access(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Только вы можете купить доступ для себя!", ephemeral=True)
            return
        
        # Проверяем баланс
        user_account = get_or_create_account(self.user.id, settings.TEST_GUILD_ID)
        room_cost = settings.LOVE_ROOM_ACCESS_COST
        
        if user_account[0] < room_cost:  # cash - первый элемент tuple
            embed = create_embed(
                title="❌ Недостаточно средств",
                description=f"У вас недостаточно средств для покупки доступа к Love комнатам.\n"
                           f"Требуется: {room_cost} {settings.ECONOMY_SYMBOL}",
                color=EmbedColors.ERROR,
                author=interaction.user
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Списываем средства
        add_cash(self.user.id, settings.TEST_GUILD_ID, -room_cost)
        
        # Добавляем доступ
        success = add_love_room_access(self.user.id, 1)
        
        if success:
            expiry_date = get_love_room_access_expiry(self.user.id)
            expiry_str = datetime.fromisoformat(expiry_date).strftime('%d.%m.%Y')
            
            # Получаем информацию о паре для обновления embed
            couple = get_couple_by_user(self.user.id)
            if couple:
                # Получаем информацию о партнере
                partner_id = couple['user2_id'] if couple['user1_id'] == self.user.id else couple['user1_id']
                partner = self.bot.get_user(partner_id)
                
                if partner:
                    # Получаем общее время в голосовых каналах
                    total_time = get_total_voice_time(couple['id'])
                    time_str = self.format_time(total_time)
                    
                    # Получаем количество дней вместе
                    days_together = self.get_days_together(couple['created_at'])
                    
                    # Создаем обновленный embed профиля пары
                    embed = create_embed(
                        title="💕 Информация о паре",
                        description=couple['description'],
                        color=EmbedColors.SUCCESS,
                        author=interaction.user
                    )
                    
                    # Добавляем поля
                    embed.add_field(
                        name="Время проведенное в лавруме:",
                        value=f"`{time_str}`",
                        inline=False
                    )
                    
                    embed.add_field(
                        name="Счастливая пара",
                        value=f"👥 {interaction.user.display_name} и {partner.display_name}",
                        inline=False
                    )
                    
                    embed.add_field(
                        name="Дата создания пары",
                        value=f"`{datetime.fromisoformat(couple['created_at']).strftime('%d.%m.%Y')}`",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="Вместе уже",
                        value=f"`{days_together} дней`",
                        inline=True
                    )
                    
                    # Добавляем информацию о доступе к love комнатам
                    embed.add_field(
                        name="💕 Love комнаты доступны еще",
                        value=f"`{expiry_str}`",
                        inline=False
                    )
                    
                    # Устанавливаем аватар партнера как изображение
                    if partner.display_avatar:
                        embed.set_image(url=partner.display_avatar.url)
                else:
                    # Если партнер не найден, показываем простое сообщение
                    embed = create_embed(
                        title="💕 Доступ к Love комнатам куплен!",
                        description=f"Поздравляем! Теперь вы можете создавать Love комнаты!\n"
                                   f"Доступ действителен до: {expiry_str}\n"
                                   f"Стоимость: {room_cost} {settings.ECONOMY_SYMBOL}",
                        color=EmbedColors.SUCCESS,
                        author=interaction.user
                    )
            else:
                # Если пользователь не в паре, показываем простое сообщение
                embed = create_embed(
                    title="💕 Доступ к Love комнатам куплен!",
                    description=f"Поздравляем! Теперь вы можете создавать Love комнаты!\n"
                               f"Доступ действителен до: {expiry_str}\n"
                               f"Стоимость: {room_cost} {settings.ECONOMY_SYMBOL}",
                    color=EmbedColors.SUCCESS,
                    author=interaction.user
                )
            
            # Отключаем кнопку
            button.disabled = True
            button.label = "✅ Доступ куплен"
            
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            # Возвращаем деньги при ошибке
            add_cash(self.user.id, settings.TEST_GUILD_ID, room_cost)
            embed = create_embed(
                title="❌ Ошибка",
                description="Не удалось купить доступ. Деньги возвращены.",
                color=EmbedColors.ERROR,
                author=interaction.user
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

class LoveCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_rooms = {}  # {channel_id: couple_id}
        
    async def cog_load(self):
        """Инициализация при загрузке кога"""
        init_love_db()
        
        # Очищаем активные сессии при запуске
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM active_sessions")
            conn.commit()
            logging.info("🧹 Очищены активные сессии при запуске")
        except Exception as e:
            logging.error(f"Ошибка при очистке активных сессий: {e}")
        finally:
            conn.close()
        
        logging.info("💕 Love cog загружен")
        
        # Запускаем задачи
        self.cleanup_task.start()
        self.monthly_payment_task.start()
    
    async def cog_unload(self):
        """Очистка при выгрузке кога"""
        self.cleanup_task.cancel()
        self.monthly_payment_task.cancel()
        self.periodic_save_task.cancel()
        logging.info("💕 Love cog выгружен")
    
    @tasks.loop(hours=1)
    async def cleanup_task(self):
        """Периодическая очистка устаревших сессий и доступов"""
        try:
            cleaned = cleanup_expired_sessions()
            if cleaned > 0:
                logging.info(f"🧹 Очищено {cleaned} устаревших сессий")
            
            # Очищаем истекшие доступы к love комнатам
            expired_access = remove_expired_access()
            if expired_access > 0:
                logging.info(f"🧹 Удалено {expired_access} истекших доступов к Love комнатам")
        except Exception as e:
            logging.error(f"Ошибка при очистке: {e}")
    
    @tasks.loop(hours=24)  # Проверяем каждый день
    async def monthly_payment_task(self):
        """Ежемесячное списание за love комнаты"""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Получаем всех пользователей с активным доступом, у которых прошло 30 дней с последнего платежа
            cursor.execute("""
                SELECT user_id, created_at FROM love_room_access 
                WHERE expires_at > datetime('now')
                AND date(created_at) <= date('now', '-30 days')
            """)
            
            users_with_access = cursor.fetchall()
            conn.close()
            
            if not users_with_access:
                logging.info("💳 Нет пользователей для ежемесячного списания")
                return
            
            monthly_cost = settings.LOVE_ROOM_ACCESS_COST
            successful_payments = 0
            failed_payments = 0
            
            for user_row in users_with_access:
                user_id = user_row['user_id']
                
                # Получаем аккаунт пользователя
                account = get_or_create_account(user_id, settings.TEST_GUILD_ID)
                
                if account[0] >= monthly_cost:  # cash - первый элемент tuple
                    # Списываем средства
                    add_cash(user_id, settings.TEST_GUILD_ID, -monthly_cost)
                    successful_payments += 1
                    logging.info(f"💳 Ежемесячная оплата Love комнат: {user_id} - {monthly_cost}")
                    
                    # Обновляем дату создания доступа (это будет дата последнего платежа)
                    add_love_room_access(user_id, 1)  # Продлеваем на месяц
                    
                    # Отправляем уведомление пользователю
                    try:
                        user = self.bot.get_user(user_id)
                        if user:
                            embed = create_embed(
                                title="💳 Ежемесячная оплата Love комнат",
                                description=f"С вашего счета списано {monthly_cost} {settings.ECONOMY_SYMBOL} за доступ к Love комнатам.\n"
                                           f"Доступ продлен на 30 дней.",
                                color=EmbedColors.SUCCESS
                            )
                            await user.send(embed=embed)
                    except Exception as e:
                        logging.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")
                else:
                    # Удаляем доступ, если нет средств
                    remove_expired_access()  # Это удалит истекшие доступы
                    failed_payments += 1
                    logging.info(f"❌ Недостаточно средств для Love комнат: {user_id}")
                    
                    # Отправляем уведомление о недостатке средств
                    try:
                        user = self.bot.get_user(user_id)
                        if user:
                            embed = create_embed(
                                title="❌ Недостаточно средств",
                                description=f"У вас недостаточно средств для оплаты Love комнат.\n"
                                           f"Требуется: {monthly_cost} {settings.ECONOMY_SYMBOL}\n"
                                           f"Доступ к Love комнатам приостановлен.",
                                color=EmbedColors.ERROR
                            )
                            await user.send(embed=embed)
                    except Exception as e:
                        logging.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")
            
            if successful_payments > 0 or failed_payments > 0:
                logging.info(f"💳 Ежемесячная оплата Love комнат: успешно {successful_payments}, неудачно {failed_payments}")
                
        except Exception as e:
            logging.error(f"Ошибка при ежемесячном списании: {e}")
    
    @tasks.loop(minutes=5)  # Каждые 5 минут
    async def periodic_save_task(self):
        """Периодическое сохранение активных сессий"""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Получаем все активные сессии
            cursor.execute("""
                SELECT * FROM active_sessions
            """)
            
            active_sessions = cursor.fetchall()
            conn.close()
            
            if not active_sessions:
                return
            
            current_time = datetime.utcnow()
            saved_sessions = 0
            
            for session in active_sessions:
                try:
                    # Вычисляем продолжительность
                    started_at = datetime.fromisoformat(session['started_at'])
                    duration = int((current_time - started_at).total_seconds())
                    
                    # Сохраняем промежуточный результат (каждые 5 минут = 300 секунд)
                    if duration >= 300:  # 5 минут
                        # Создаем новое подключение для каждой сессии
                        conn = get_connection()
                        cursor = conn.cursor()
                        
                        # Сохраняем в историю
                        cursor.execute("""
                            INSERT INTO voice_sessions (couple_id, channel_id, started_at, ended_at, duration_seconds)
                            VALUES (?, ?, ?, ?, ?)
                        """, (session['couple_id'], session['channel_id'], session['started_at'], 
                              current_time.isoformat(), duration))
                        
                        # Обновляем время начала сессии
                        cursor.execute("""
                            UPDATE active_sessions 
                            SET started_at = ? 
                            WHERE id = ?
                        """, (current_time.isoformat(), session['id']))
                        
                        conn.commit()
                        conn.close()
                        saved_sessions += 1
                        logging.info(f"💾 Промежуточное сохранение сессии пары {session['couple_id']}: {duration} секунд")
                        
                except Exception as e:
                    logging.error(f"Ошибка при сохранении сессии {session['id']}: {e}")
            
            if saved_sessions > 0:
                logging.info(f"💾 Промежуточно сохранено {saved_sessions} сессий")
                
        except Exception as e:
            logging.error(f"Ошибка при периодическом сохранении: {e}")
    
    def format_time(self, seconds: int) -> str:
        """Форматирование времени в часы:минуты:секунды"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours} часов {minutes} минут {secs} секунд"
    
    def get_days_together(self, created_at: str) -> int:
        """Получить количество дней вместе"""
        created = datetime.fromisoformat(created_at)
        return (datetime.now() - created).days
    
    @app_commands.command(name="love", description="Показать профиль вашей пары")
    async def love_profile(self, interaction: discord.Interaction):
        """Команда для показа профиля пары"""
        try:
            # Получаем информацию о паре
            couple = get_couple_by_user(interaction.user.id)
            
            if not couple:
                embed = create_embed(
                    title="💔 Пара не найдена",
                    description="Вы пока не состоите в паре. Найдите свою вторую половинку!",
                    color=EmbedColors.WARNING,
                    author=interaction.user
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Получаем информацию о партнере
            partner_id = couple['user2_id'] if couple['user1_id'] == interaction.user.id else couple['user1_id']
            partner = self.bot.get_user(partner_id)
            
            if not partner:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Не удалось найти информацию о вашем партнере.",
                    color=EmbedColors.ERROR,
                    author=interaction.user
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Получаем общее время в голосовых каналах
            total_time = get_total_voice_time(couple['id'])
            time_str = self.format_time(total_time)
            
            # Получаем количество дней вместе
            days_together = self.get_days_together(couple['created_at'])
            
            # Проверяем доступ к love комнатам
            has_access = has_love_room_access(interaction.user.id)
            access_expiry = get_love_room_access_expiry(interaction.user.id)
            
            # Создаем embed
            embed = create_embed(
                title="💕 Информация о паре",
                description=couple['description'],
                color=EmbedColors.SUCCESS,
                author=interaction.user
            )
            
            # Добавляем поля
            embed.add_field(
                name="Время проведенное в лавруме:",
                value=f"`{time_str}`",
                inline=False
            )
            
            embed.add_field(
                name="Счастливая пара",
                value=f"👥 {interaction.user.display_name} и {partner.display_name}",
                inline=False
            )
            
            embed.add_field(
                name="Дата создания пары",
                value=f"`{datetime.fromisoformat(couple['created_at']).strftime('%d.%m.%Y')}`",
                inline=True
            )
            
            embed.add_field(
                name="Вместе уже",
                value=f"`{days_together} дней`",
                inline=True
            )
            
            # Добавляем информацию о доступе к love комнатам
            if has_access and access_expiry:
                expiry_str = datetime.fromisoformat(access_expiry).strftime('%d.%m.%Y')
                embed.add_field(
                    name="💕 Love комнаты доступны еще",
                    value=f"`{expiry_str}`",
                    inline=False
                )
            
            # Устанавливаем аватар партнера как изображение
            if partner.display_avatar:
                embed.set_image(url=partner.display_avatar.url)
            
            # Создаем view с кнопкой покупки доступа, если его нет
            if not has_access:
                view = LoveRoomAccessView(interaction.user, self.bot)
                await interaction.response.send_message(embed=embed, view=view)
            else:
                await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logging.error(f"Ошибка в команде love: {e}")
            if not interaction.response.is_done():
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Произошла ошибка при получении информации о паре.",
                    color=EmbedColors.ERROR,
                    author=interaction.user
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="marry", description="Предложить создать пару с другим пользователем")
    @app_commands.describe(user="Пользователь, с которым хотите создать пару")
    async def marry(self, interaction: discord.Interaction, user: discord.Member):
        """Команда для создания пары с подтверждением"""
        try:
            # Проверяем, что пользователь не пытается создать пару с самим собой
            if user.id == interaction.user.id:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Вы не можете создать пару с самим собой!",
                    color=EmbedColors.ERROR,
                    author=interaction.user
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Проверяем, что пользователь не состоит уже в паре
            existing_couple = get_couple_by_user(interaction.user.id)
            if existing_couple:
                embed = create_embed(
                    title="❌ Уже в паре",
                    description="Вы уже состоите в паре!",
                    color=EmbedColors.ERROR,
                    author=interaction.user
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Проверяем, что целевой пользователь не состоит в паре
            target_couple = get_couple_by_user(user.id)
            if target_couple:
                embed = create_embed(
                    title="❌ Пользователь уже в паре",
                    description=f"{user.display_name} уже состоит в паре!",
                    color=EmbedColors.ERROR,
                    author=interaction.user
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Создаем предложение о создании пары
            embed = create_embed(
                title="💕 Предложение о создании пары",
                description=f"{interaction.user.display_name} предлагает создать пару с {user.display_name}!\n\n"
                           f"У вас есть 60 секунд, чтобы принять или отклонить предложение.",
                color=EmbedColors.INFO,
                author=interaction.user
            )
            
            view = MarryConfirmationView(interaction.user, user, timeout=60.0)
            await interaction.response.send_message(embed=embed, view=view)
                
        except Exception as e:
            logging.error(f"Ошибка в команде marry: {e}")
            embed = create_embed(
                title="❌ Ошибка",
                description="Произошла ошибка при создании предложения.",
                color=EmbedColors.ERROR,
                author=interaction.user
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="divorce", description="Расторгнуть пару")
    async def divorce(self, interaction: discord.Interaction):
        """Команда для расторжения пары"""
        try:
            # Получаем информацию о паре
            couple = get_couple_by_user(interaction.user.id)
            
            if not couple:
                embed = create_embed(
                    title="❌ Пара не найдена",
                    description="Вы не состоите в паре.",
                    color=EmbedColors.ERROR,
                    author=interaction.user
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Расторгаем пару
            success = delete_couple(couple['id'])
            
            if success:
                embed = create_embed(
                    title="💔 Пара расторгнута",
                    description="Ваша пара была расторгнута.",
                    color=EmbedColors.WARNING,
                    author=interaction.user
                )
                await interaction.response.send_message(embed=embed)
            else:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Не удалось расторгнуть пару.",
                    color=EmbedColors.ERROR,
                    author=interaction.user
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except Exception as e:
            logging.error(f"Ошибка в команде divorce: {e}")
            embed = create_embed(
                title="❌ Ошибка",
                description="Произошла ошибка при расторжении пары.",
                color=EmbedColors.ERROR,
                author=interaction.user
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="clear_all_couples", description="Удалить все пары из базы данных (только для администраторов)")
    @app_commands.default_permissions(administrator=True)
    async def clear_all_couples_command(self, interaction: discord.Interaction):
        """Команда для удаления всех пар"""
        try:
            # Удаляем все пары
            success = clear_all_couples()
            
            if success:
                embed = create_embed(
                    title="✅ Все пары удалены",
                    description="Все пары успешно удалены из базы данных.",
                    color=EmbedColors.SUCCESS,
                    author=interaction.user
                )
            else:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Произошла ошибка при удалении пар.",
                    color=EmbedColors.ERROR,
                    author=interaction.user
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logging.error(f"Ошибка в команде clear_all_couples: {e}")
            embed = create_embed(
                title="❌ Ошибка",
                description="Произошла ошибка при выполнении команды.",
                color=EmbedColors.ERROR,
                author=interaction.user
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _kick_from_love_room(self, member: discord.Member, reason: str):
        """Кикает пользователя из лаврумы и отправляет уведомление в ЛС"""
        try:
            # Перемещаем пользователя из голосового канала
            await member.move_to(None, reason=reason)
            
            # Создаем эмбед для уведомления
            embed = create_embed(
                title="🚫 Доступ к Love комнатам запрещен",
                description=reason,
                color=EmbedColors.ERROR,
                author=member
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            
            # Отправляем уведомление в ЛС
            try:
                await member.send(embed=embed)
            except discord.Forbidden:
                # Если не можем отправить в ЛС, логируем
                logging.warning(f"Не удалось отправить уведомление в ЛС пользователю {member.display_name}")
            
            logging.info(f"Пользователь {member.display_name} кикнут из лаврумы: {reason}")
            
        except Exception as e:
            logging.error(f"Ошибка при кике пользователя {member.display_name} из лаврумы: {e}")
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Обработка событий голосовых каналов"""
        try:
            logging.info(f"Voice state update: {member.display_name} - {before.channel} -> {after.channel}")
            
            # Проверка при входе в лавруму (голосовой канал для создания love комнат)
            if (after.channel and 
                after.channel.id == settings.LOVE_VOICE_CHANNEL_ID and 
                not before.channel):
                
                # Проверяем, что пользователь состоит в паре
                couple = get_couple_by_user(member.id)
                if not couple:
                    logging.info(f"Пользователь {member.display_name} зашел в лавруму без пары")
                    await self._kick_from_love_room(member, "У вас нет пары для создания love комнаты")
                    return
                
                # Проверяем доступ к love комнатам
                if not has_love_room_access(member.id):
                    logging.info(f"У пользователя {member.display_name} нет доступа к love комнатам")
                    await self._kick_from_love_room(member, "У вас нет доступа к love комнатам. Купите доступ в магазине!")
                    return
                
                # Если все проверки пройдены, продолжаем обычную логику
                logging.info(f"Пользователь {member.display_name} прошел все проверки для лаврумы")
            
            # Проверяем, что пользователь состоит в паре (для остальной логики)
            couple = get_couple_by_user(member.id)
            if not couple:
                logging.info(f"Пользователь {member.display_name} не состоит в паре")
                return
            
            logging.info(f"Пользователь {member.display_name} состоит в паре {couple['id']}")
            
            # Если пользователь зашел в специальный канал для создания love комнат
            if (after.channel and 
                after.channel.id == settings.LOVE_VOICE_CHANNEL_ID and 
                not before.channel):
                
                logging.info(f"Пользователь {member.display_name} зашел в канал создания love комнат")
                
                # Проверяем, есть ли уже активная сессия
                active_session = get_active_session(couple['id'])
                if active_session:
                    logging.info(f"У пары {couple['id']} уже есть активная сессия")
                    return
                
                # Создаем голосовую комнату для пары
                guild = member.guild
                category = guild.get_channel(settings.LOVE_CATEGORY_ID)
                
                if not category:
                    logging.error(f"Категория {settings.LOVE_CATEGORY_ID} не найдена")
                    return
                
                # Получаем информацию о партнере
                partner_id = couple['user2_id'] if couple['user1_id'] == member.id else couple['user1_id']
                partner = guild.get_member(partner_id)
                
                if not partner:
                    logging.error(f"Партнер {partner_id} не найден в гильдии")
                    return
                
                logging.info(f"Создаем love комнату для {member.display_name} и {partner.display_name}")
                
                # Создаем голосовой канал
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(connect=False),
                    member: discord.PermissionOverwrite(connect=True),
                    partner: discord.PermissionOverwrite(connect=True)
                }
                
                channel_name = f"{member.display_name} ❤️ {partner.display_name}"
                voice_channel = await guild.create_voice_channel(
                    name=channel_name,
                    category=category,
                    overwrites=overwrites,
                    user_limit=2  # Лимит на 2 пользователя
                )
                
                logging.info(f"Создан голосовой канал {voice_channel.id}")
                
                # Перемещаем пользователя в новый канал
                await member.move_to(voice_channel)
                logging.info(f"Пользователь {member.display_name} перемещен в канал {voice_channel.id}")
                
                # Пока не начинаем отслеживание времени - ждем пока оба пользователя будут в комнате
                self.active_rooms[voice_channel.id] = couple['id']
                
                logging.info(f"Создана love комната {voice_channel.id} для пары {couple['id']}")
            
            # Если пользователь зашел в love комнату (проверяем, что оба пользователя в комнате)
            elif (after.channel and 
                  after.channel.id in self.active_rooms):
                
                couple_id = self.active_rooms[after.channel.id]
                couple = get_couple_by_id(couple_id)
                
                if couple:
                    guild = member.guild
                    # Проверяем, находятся ли оба пользователя в комнате
                    user1 = guild.get_member(couple['user1_id'])
                    user2 = guild.get_member(couple['user2_id'])
                    
                    if (user1 and user1.voice and user1.voice.channel.id == after.channel.id and
                        user2 and user2.voice and user2.voice.channel.id == after.channel.id):
                        
                        # Оба пользователя в комнате, начинаем отслеживание времени
                        active_session = get_active_session(couple_id)
                        if not active_session:
                            start_voice_session(couple_id, after.channel.id)
                            logging.info(f"Начато отслеживание времени для пары {couple_id}")
            
            # Если пользователь покинул love комнату
            elif (before.channel and 
                  before.channel.id in self.active_rooms and 
                  not after.channel):
                
                couple_id = self.active_rooms[before.channel.id]
                couple = get_couple_by_id(couple_id)
                
                if couple:
                    guild = member.guild
                    # Проверяем, остался ли кто-то из пары в комнате
                    user1 = guild.get_member(couple['user1_id'])
                    user2 = guild.get_member(couple['user2_id'])
                    
                    # Проверяем, есть ли кто-то из пары в комнате
                    someone_in_room = False
                    if user1 and user1.voice and user1.voice.channel.id == before.channel.id:
                        someone_in_room = True
                    if user2 and user2.voice and user2.voice.channel.id == before.channel.id:
                        someone_in_room = True
                    
                    if not someone_in_room:
                        # Никого из пары не осталось в комнате, завершаем сессию и удаляем канал
                        duration = end_voice_session(couple_id)
                        
                        if duration:
                            logging.info(f"Сессия завершена для пары {couple_id}, продолжительность: {duration} секунд")
                        
                        # Удаляем канал
                        try:
                            await before.channel.delete(reason="Love комната - никто из пары не остался в канале")
                        except Exception as e:
                            logging.error(f"Ошибка при удалении канала {before.channel.id}: {e}")
                        
                        # Удаляем из активных комнат
                        del self.active_rooms[before.channel.id]
                    else:
                        # Кто-то из пары остался в комнате, просто завершаем сессию
                        duration = end_voice_session(couple_id)
                        if duration:
                            logging.info(f"Сессия завершена для пары {couple_id}, продолжительность: {duration} секунд")
            
            # Если пользователь перешел из love комнаты в другой канал
            elif (before.channel and 
                  before.channel.id in self.active_rooms and 
                  after.channel and 
                  after.channel.id != before.channel.id):
                
                couple_id = self.active_rooms[before.channel.id]
                couple = get_couple_by_id(couple_id)
                
                if couple:
                    guild = member.guild
                    # Проверяем, остался ли кто-то из пары в комнате
                    user1 = guild.get_member(couple['user1_id'])
                    user2 = guild.get_member(couple['user2_id'])
                    
                    # Проверяем, есть ли кто-то из пары в комнате
                    someone_in_room = False
                    if user1 and user1.voice and user1.voice.channel.id == before.channel.id:
                        someone_in_room = True
                    if user2 and user2.voice and user2.voice.channel.id == before.channel.id:
                        someone_in_room = True
                    
                    if not someone_in_room:
                        # Никого из пары не осталось в комнате, завершаем сессию и удаляем канал
                        duration = end_voice_session(couple_id)
                        
                        if duration:
                            logging.info(f"Сессия завершена для пары {couple_id}, продолжительность: {duration} секунд")
                        
                        # Удаляем канал
                        try:
                            await before.channel.delete(reason="Love комната - никто из пары не остался в канале")
                        except Exception as e:
                            logging.error(f"Ошибка при удалении канала {before.channel.id}: {e}")
                        
                        # Удаляем из активных комнат
                        del self.active_rooms[before.channel.id]
                    else:
                        # Кто-то из пары остался в комнате, просто завершаем сессию
                        duration = end_voice_session(couple_id)
                        if duration:
                            logging.info(f"Сессия завершена для пары {couple_id}, продолжительность: {duration} секунд")
                
        except Exception as e:
            logging.error(f"Ошибка в обработке голосовых событий: {e}")

async def setup(bot):
    await bot.add_cog(LoveCog(bot))
