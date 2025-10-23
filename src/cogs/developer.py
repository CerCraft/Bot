"""
Ког с тестовыми командами для разработчика
"""
import discord
from discord.ext import commands
from discord import app_commands
from src.core.config import settings
from src.database.economy import get_cooldowns, set_cooldown, get_or_create_account, get_notifications_enabled
from src.utils.embed import create_embed, EmbedColors
from src.database.clans import (
    init_clans_db,
    get_clan_by_id,
    get_user_clan,
    get_clan_members,
    add_clan_member,
    remove_clan_member,
    get_all_clans,
    deactivate_clan,
    get_clan_voice_channels,
    get_connection
)
import time
import logging


class DeveloperCog(commands.Cog):
    """Ког с командами для разработчика"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    def _is_developer(self, user: discord.Member) -> bool:
        """Проверяет, является ли пользователь разработчиком"""
        # Проверяем по ролям из конфига
        dev_roles = getattr(settings, 'DEVELOPER_ROLES', [])
        if dev_roles:
            user_roles = [role.id for role in user.roles]
            return any(role_id in dev_roles for role_id in user_roles)
        
        # Проверяем по правам администратора
        return user.guild_permissions.administrator
    
    async def _send_notification(self, member: discord.Member, command_name: str, guild: discord.Guild):
        """Отправляет уведомление пользователю о готовности команды"""
        try:
            # Проверяем, включены ли уведомления у пользователя
            if not get_notifications_enabled(member.id, guild.id):
                return
            
            # Создаем embed уведомления
            embed = discord.Embed(
                title="🔔 Уведомление о готовности команды",
                description=f"Команда `/{command_name}` теперь доступна!",
                color=discord.Color.from_str("#45248e")
            )
            embed.set_footer(text="Вы можете отключить эти уведомления в команде /balance")
            
            # Отправляем в ЛС
            await member.send(embed=embed)
        except discord.Forbidden:
            # Пользователь заблокировал бота или закрыл ЛС
            pass
        except Exception as e:
            print(f"Ошибка при отправке уведомления пользователю {member.id}: {e}")
    
    @app_commands.command(name="reset_cooldowns", description="Сбросить кулдауны пользователя")
    async def reset_cooldowns(self, interaction: discord.Interaction, member: discord.Member):
        """Сбрасывает все кулдауны пользователя"""
        if not self._is_developer(interaction.user):
            await interaction.response.send_message("❌ Нет доступа к командам разработчика.", ephemeral=True)
            return
        
        # Сбрасываем все кулдауны
        set_cooldown(member.id, interaction.guild.id, 'daily_cd', 0)
        set_cooldown(member.id, interaction.guild.id, 'work_cd', 0)
        set_cooldown(member.id, interaction.guild.id, 'weekly_cd', 0)
        set_cooldown(member.id, interaction.guild.id, 'rob_cd', 0)
        
        # Отправляем уведомления для всех команд
        await self._send_notification(member, "daily", interaction.guild)
        await self._send_notification(member, "work", interaction.guild)
        await self._send_notification(member, "weekly", interaction.guild)
        
        await interaction.response.send_message(f"✅ Кулдауны пользователя {member.mention} сброшены.", ephemeral=False)
    
    @app_commands.command(name="reset_daily", description="Сбросить кулдаун daily")
    async def reset_daily(self, interaction: discord.Interaction, member: discord.Member):
        """Сбрасывает кулдаун daily"""
        if not self._is_developer(interaction.user):
            await interaction.response.send_message("❌ Нет доступа к командам разработчика.", ephemeral=True)
            return
        
        set_cooldown(member.id, interaction.guild.id, 'daily_cd', 0)
        
        # Отправляем уведомление пользователю
        await self._send_notification(member, "daily", interaction.guild)
        
        await interaction.response.send_message(f"✅ Кулдаун daily для {member.mention} сброшен.", ephemeral=False)
    
    @app_commands.command(name="reset_work", description="Сбросить кулдаун work")
    async def reset_work(self, interaction: discord.Interaction, member: discord.Member):
        """Сбрасывает кулдаун work"""
        if not self._is_developer(interaction.user):
            await interaction.response.send_message("❌ Нет доступа к командам разработчика.", ephemeral=True)
            return
        
        set_cooldown(member.id, interaction.guild.id, 'work_cd', 0)
        
        # Отправляем уведомление пользователю
        await self._send_notification(member, "work", interaction.guild)
        
        await interaction.response.send_message(f"✅ Кулдаун work для {member.mention} сброшен.", ephemeral=False)
    
    @app_commands.command(name="reset_weekly", description="Сбросить кулдаун weekly")
    async def reset_weekly(self, interaction: discord.Interaction, member: discord.Member):
        """Сбрасывает кулдаун weekly"""
        if not self._is_developer(interaction.user):
            await interaction.response.send_message("❌ Нет доступа к командам разработчика.", ephemeral=True)
            return
        
        set_cooldown(member.id, interaction.guild.id, 'weekly_cd', 0)
        
        # Отправляем уведомление пользователю
        await self._send_notification(member, "weekly", interaction.guild)
        
        await interaction.response.send_message(f"✅ Кулдаун weekly для {member.mention} сброшен.", ephemeral=False)
    
    @app_commands.command(name="reset_rob", description="Сбросить кулдаун rob")
    async def reset_rob(self, interaction: discord.Interaction, member: discord.Member):
        """Сбрасывает кулдаун rob"""
        if not self._is_developer(interaction.user):
            await interaction.response.send_message("❌ Нет доступа к командам разработчика.", ephemeral=True)
            return
        
        set_cooldown(member.id, interaction.guild.id, 'rob_cd', 0)
        await interaction.response.send_message(f"✅ Кулдаун rob для {member.mention} сброшен.", ephemeral=False)
    
    @app_commands.command(name="check_cooldowns", description="Проверить кулдауны пользователя")
    async def check_cooldowns(self, interaction: discord.Interaction, member: discord.Member):
        """Показывает текущие кулдауны пользователя"""
        if not self._is_developer(interaction.user):
            await interaction.response.send_message("❌ Нет доступа к командам разработчика.", ephemeral=True)
            return
        
        cds = get_cooldowns(member.id, interaction.guild.id)
        now = int(time.time())
        
        if not cds:
            await interaction.response.send_message(f"ℹ️ У {member.mention} нет активных кулдаунов.", ephemeral=False)
            return
        
        daily_cd, work_cd, weekly_cd, rob_cd, arrest_until = cds
        
        embed = discord.Embed(
            title=f"Кулдауны {member.display_name}",
            color=discord.Color.blue()
        )
        
        def format_cd(cd_timestamp, name):
            if not cd_timestamp or cd_timestamp <= now:
                return f"✅ {name}: доступно"
            else:
                remaining = cd_timestamp - now
                hours = remaining // 3600
                minutes = (remaining % 3600) // 60
                seconds = remaining % 60
                return f"⏰ {name}: {hours:02d}:{minutes:02d}:{seconds:02d}"
        
        embed.add_field(
            name="Статус кулдаунов",
            value=(
                f"{format_cd(daily_cd, 'Daily')}\n"
                f"{format_cd(work_cd, 'Work')}\n"
                f"{format_cd(weekly_cd, 'Weekly')}\n"
                f"{format_cd(rob_cd, 'Rob')}\n"
                f"{format_cd(arrest_until, 'Arrest')}"
            ),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=False)
    
    @app_commands.command(name="force_daily", description="Принудительно выполнить daily")
    async def force_daily(self, interaction: discord.Interaction, member: discord.Member):
        """Принудительно выполняет daily для пользователя"""
        if not self._is_developer(interaction.user):
            await interaction.response.send_message("❌ Нет доступа к командам разработчика.", ephemeral=True)
            return
        
        # Создаем аккаунт если не существует
        get_or_create_account(member.id, interaction.guild.id)
        
        # Начисляем daily
        from src.database.economy import add_bank
        daily_amount = getattr(settings, 'ECONOMY_DAILY_AMOUNT', 250)
        add_bank(member.id, interaction.guild.id, daily_amount)
        
        # Устанавливаем кулдаун
        daily_cd_sec = getattr(settings, 'ECONOMY_DAILY_COOLDOWN_SECONDS', 86400)
        next_time = int(time.time() + daily_cd_sec)
        set_cooldown(member.id, interaction.guild.id, 'daily_cd', next_time)
        
        await interaction.response.send_message(f"✅ Daily выполнен для {member.mention}. Начислено: {daily_amount}💰", ephemeral=False)
    
    @app_commands.command(name="force_work", description="Принудительно выполнить work")
    async def force_work(self, interaction: discord.Interaction, member: discord.Member):
        """Принудительно выполняет work для пользователя"""
        if not self._is_developer(interaction.user):
            await interaction.response.send_message("❌ Нет доступа к командам разработчика.", ephemeral=True)
            return
        
        # Создаем аккаунт если не существует
        get_or_create_account(member.id, interaction.guild.id)
        
        # Начисляем work
        from src.database.economy import add_bank
        work_amount = getattr(settings, 'ECONOMY_WORK_AMOUNT', 150)
        add_bank(member.id, interaction.guild.id, work_amount)
        
        # Устанавливаем кулдаун
        work_cd_sec = getattr(settings, 'ECONOMY_WORK_COOLDOWN_SECONDS', 3600)
        next_time = int(time.time() + work_cd_sec)
        set_cooldown(member.id, interaction.guild.id, 'work_cd', next_time)
        
        await interaction.response.send_message(f"✅ Work выполнен для {member.mention}. Начислено: {work_amount}💰", ephemeral=False)
    
    @app_commands.command(name="force_weekly", description="Принудительно выполнить weekly")
    async def force_weekly(self, interaction: discord.Interaction, member: discord.Member):
        """Принудительно выполняет weekly для пользователя"""
        if not self._is_developer(interaction.user):
            await interaction.response.send_message("❌ Нет доступа к командам разработчика.", ephemeral=True)
            return
        
        # Создаем аккаунт если не существует
        get_or_create_account(member.id, interaction.guild.id)
        
        # Начисляем weekly
        from src.database.economy import add_bank
        weekly_amount = getattr(settings, 'ECONOMY_WEEKLY_AMOUNT', 1000)
        add_bank(member.id, interaction.guild.id, weekly_amount)
        
        # Устанавливаем кулдаун
        weekly_cd_sec = getattr(settings, 'ECONOMY_WEEKLY_COOLDOWN_SECONDS', 604800)
        next_time = int(time.time() + weekly_cd_sec)
        set_cooldown(member.id, interaction.guild.id, 'weekly_cd', next_time)
        
        await interaction.response.send_message(f"✅ Weekly выполнен для {member.mention}. Начислено: {weekly_amount}💰", ephemeral=False)
    
    @app_commands.command(name="dev_info", description="Информация о боте для разработчика")
    async def dev_info(self, interaction: discord.Interaction):
        """Показывает техническую информацию о боте"""
        if not self._is_developer(interaction.user):
            await interaction.response.send_message("❌ Нет доступа к командам разработчика.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🔧 Информация о боте",
            color=discord.Color.green()
        )
        
        # Информация о боте
        embed.add_field(
            name="Бот",
            value=(
                f"**Имя:** {self.bot.user.name}\n"
                f"**ID:** {self.bot.user.id}\n"
                f"**Серверов:** {len(self.bot.guilds)}\n"
                f"**Пользователей:** {len(self.bot.users)}"
            ),
            inline=True
        )
        
        # Информация о сервере
        embed.add_field(
            name="Сервер",
            value=(
                f"**Имя:** {interaction.guild.name}\n"
                f"**ID:** {interaction.guild.id}\n"
                f"**Участников:** {interaction.guild.member_count}\n"
                f"**Каналов:** {len(interaction.guild.channels)}"
            ),
            inline=True
        )
        
        # Настройки экономики
        daily_amount = getattr(settings, 'ECONOMY_DAILY_AMOUNT', 250)
        work_amount = getattr(settings, 'ECONOMY_WORK_AMOUNT', 150)
        weekly_amount = getattr(settings, 'ECONOMY_WEEKLY_AMOUNT', 1000)
        
        embed.add_field(
            name="Настройки экономики",
            value=(
                f"**Daily:** {daily_amount}💰\n"
                f"**Work:** {work_amount}💰\n"
                f"**Weekly:** {weekly_amount}💰"
            ),
            inline=True
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=False)
    
    @commands.command(name="help_developer")
    async def help_developer(self, ctx):
        """Показывает список команд для разработчика"""
        if not self._is_developer(ctx.author):
            await ctx.send("❌ Нет доступа к командам разработчика.")
            return
        
        embed = discord.Embed(
            title="🔧 Команды разработчика",
            description="Список доступных команд для разработки и тестирования",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="Сброс кулдаунов",
            value=(
                "`/reset_cooldowns @user` - сбросить все кулдауны\n"
                "`/reset_daily @user` - сбросить кулдаун daily\n"
                "`/reset_work @user` - сбросить кулдаун work\n"
                "`/reset_weekly @user` - сбросить кулдаун weekly\n"
                "`/reset_rob @user` - сбросить кулдаун rob"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Принудительное выполнение",
            value=(
                "`/force_daily @user` - принудительно выполнить daily\n"
                "`/force_work @user` - принудительно выполнить work\n"
                "`/force_weekly @user` - принудительно выполнить weekly"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Информация",
            value=(
                "`/check_cooldowns @user` - проверить кулдауны пользователя\n"
                "`/dev_info` - информация о боте"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Префиксные команды",
            value=(
                "`!help_developer` - показать эту справку"
            ),
            inline=False
        )
        
        embed.set_footer(text="Доступно только для разработчиков")
        
        await ctx.send(embed=embed)
    
    # ===== Команды управления кланами =====
    
    @app_commands.command(name="clan_find_channel", description="Поиск и настройка канала для кланов (только для администраторов)")
    @app_commands.default_permissions(administrator=True)
    async def clan_find_channel_command(self, interaction: discord.Interaction):
        """Команда для поиска подходящего канала для информационного сообщения"""
        embed = create_embed(
            title="🔍 Поиск канала для кланов",
            description="Ищем подходящий канал для информационного сообщения...",
            color=EmbedColors.INFO
        )
        
        # Ищем каналы с подходящими названиями
        suitable_channels = []
        for channel in interaction.guild.text_channels:
            if any(keyword in channel.name.lower() for keyword in ['clan', 'клан', 'info', 'инфо', 'информация']):
                permissions = channel.permissions_for(interaction.guild.me)
                if permissions.send_messages and permissions.embed_links:
                    suitable_channels.append(channel)
        
        if suitable_channels:
            embed.add_field(
                name="📢 Найденные подходящие каналы:",
                value="\n".join([f"• {ch.mention} (ID: {ch.id})" for ch in suitable_channels[:5]]),
                inline=False
            )
            
            # Предлагаем выбрать канал
            embed.add_field(
                name="💡 Рекомендация",
                value=f"Рекомендуем использовать канал {suitable_channels[0].mention}\n"
                      f"Для настройки выполните команду `/clan_set_channel` с ID: `{suitable_channels[0].id}`",
                inline=False
            )
        else:
            embed.add_field(
                name="❌ Подходящие каналы не найдены",
                value="Создайте канал с названием содержащим 'clan', 'клан', 'info' или 'инфо'",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="clan_set_channel", description="Установка канала для кланов по ID (только для администраторов)")
    @app_commands.describe(channel_id="ID канала для информационного сообщения")
    @app_commands.default_permissions(administrator=True)
    async def clan_set_channel_command(self, interaction: discord.Interaction, channel_id: str):
        """Команда для установки канала по ID"""
        try:
            channel_id_int = int(channel_id)
        except ValueError:
            embed = create_embed(
                title="❌ Ошибка",
                description="Неверный формат ID канала! Используйте только цифры.",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Проверяем, существует ли канал
        channel = self.bot.get_channel(channel_id_int)
        if not channel:
            embed = create_embed(
                title="❌ Ошибка",
                description=f"Канал с ID {channel_id_int} не найден!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Проверяем права
        permissions = channel.permissions_for(interaction.guild.me)
        if not permissions.send_messages:
            embed = create_embed(
                title="❌ Ошибка",
                description=f"Бот не имеет прав на отправку сообщений в канал {channel.mention}!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if not permissions.embed_links:
            embed = create_embed(
                title="❌ Ошибка",
                description=f"Бот не имеет прав на встраивание ссылок в канал {channel.mention}!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Временно обновляем настройку
        settings.CLAN_INFO_CHANNEL_ID = channel_id_int
        
        # Получаем Clans cog для вызова update_info_message
        clans_cog = self.bot.get_cog('Clans')
        if clans_cog:
            await clans_cog.update_info_message()
        
        embed = create_embed(
            title="✅ Канал настроен",
            description=f"Информационный канал кланов установлен: {channel.mention}\n"
                       f"ID: `{channel_id_int}`\n\n"
                       f"⚠️ **Важно:** Обновите `CLAN_INFO_CHANNEL_ID` в файле `config.py` на значение `{channel_id_int}`",
            color=EmbedColors.SUCCESS
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="clan_info", description="Создать информационное сообщение о кланах в текущем канале")
    @app_commands.default_permissions(administrator=True)
    async def clan_info_command(self, interaction: discord.Interaction):
        """Команда для создания информационного сообщения в текущем канале"""
        try:
            # Получаем список всех кланов
            clans = get_all_clans()
            
            # Импортируем CreateClanButton из clans
            from src.cogs.clans import CreateClanButton
            
            embed = create_embed(
                title="🏰 Система кланов",
                description="Создайте свой клан и пригласите друзей!",
                color=EmbedColors.INFO
            )
            
            embed.add_field(
                name="💰 Стоимость создания",
                value=f"{settings.CLAN_CREATE_COST} {settings.ECONOMY_SYMBOL}",
                inline=True
            )
            
            embed.add_field(
                name="💳 Ежемесячная плата",
                value=f"{settings.CLAN_MONTHLY_COST} {settings.ECONOMY_SYMBOL}",
                inline=True
            )
            
            embed.add_field(
                name="👥 Максимум участников",
                value=f"{settings.CLAN_DEFAULT_MAX_MEMBERS} (можно расширить)",
                inline=True
            )
            
            if clans:
                clan_list = []
                for clan in clans[:10]:  # Показываем только первые 10
                    clan_list.append(f"🏰 **{clan['name']}** - {clan['description']}")
                
                embed.add_field(
                    name="📋 Список кланов",
                    value="\n".join(clan_list) if clan_list else "Пока нет кланов",
                    inline=False
                )
            
            embed.add_field(
                name="🔧 Возможности",
                value="• Собственная роль и каналы\n"
                      "• Управление участниками\n"
                      "• Покупка дополнительных слотов\n"
                      "• Дополнительные голосовые каналы",
                inline=False
            )
            
            # Создаем обычную кнопку
            view = CreateClanButton(self.bot)
            
            # Отправляем сообщение
            message = await interaction.channel.send(embed=embed, view=view)
            
            embed_success = create_embed(
                title="✅ Информационное сообщение создано",
                description=f"Сообщение с информацией о кланах отправлено в {interaction.channel.mention}\n"
                           f"ID сообщения: `{message.id}`",
                color=EmbedColors.SUCCESS
            )
            await interaction.response.send_message(embed=embed_success, ephemeral=True)
            
        except Exception as e:
            logging.error(f"Ошибка при создании информационного сообщения: {e}")
            embed = create_embed(
                title="❌ Ошибка",
                description="Произошла ошибка при создании информационного сообщения.",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="clan_migrate", description="Миграция базы данных кланов (только для администраторов)")
    @app_commands.default_permissions(administrator=True)
    async def clan_migrate_command(self, interaction: discord.Interaction):
        """Команда для миграции базы данных кланов"""
        try:
            # Принудительно инициализируем базу данных
            init_clans_db()
            
            embed = create_embed(
                title="✅ Миграция завершена",
                description="База данных кланов успешно обновлена!\n"
                           "Добавлено поле avatar_url для всех кланов.",
                color=EmbedColors.SUCCESS
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logging.error(f"Ошибка при миграции базы данных кланов: {e}")
            embed = create_embed(
                title="❌ Ошибка миграции",
                description=f"Произошла ошибка при миграции базы данных:\n```{str(e)}```",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="clan_fix_owner", description="Исправить владельца клана (только для администраторов)")
    @app_commands.describe(clan_id="ID клана для исправления")
    @app_commands.default_permissions(administrator=True)
    async def clan_fix_owner_command(self, interaction: discord.Interaction, clan_id: int):
        """Команда для исправления владельца клана"""
        try:
            clan = get_clan_by_id(clan_id)
            if not clan:
                embed = create_embed(
                    title="❌ Клан не найден",
                    description=f"Клан с ID {clan_id} не найден.",
                    color=EmbedColors.ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Добавляем владельца как участника если его нет
            members = get_clan_members(clan_id)
            owner_found = any(member['user_id'] == clan['owner_id'] for member in members)
            
            if not owner_found:
                add_clan_member(clan_id, clan['owner_id'], 'owner')
                embed = create_embed(
                    title="✅ Владелец исправлен",
                    description=f"Владелец клана **{clan['name']}** добавлен как участник.",
                    color=EmbedColors.SUCCESS
                )
            else:
                embed = create_embed(
                    title="ℹ️ Владелец уже участник",
                    description=f"Владелец клана **{clan['name']}** уже является участником.",
                    color=EmbedColors.INFO
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logging.error(f"Ошибка при исправлении владельца клана: {e}")
            embed = create_embed(
                title="❌ Ошибка",
                description=f"Произошла ошибка при исправлении владельца:\n```{str(e)}```",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="clan_force_update_owner", description="Принудительно обновить владельца клана (только для администраторов)")
    @app_commands.describe(clan_id="ID клана", new_owner_id="ID нового владельца")
    @app_commands.default_permissions(administrator=True)
    async def clan_force_update_owner_command(self, interaction: discord.Interaction, clan_id: int, new_owner_id: int):
        """Команда для принудительного обновления владельца клана"""
        try:
            # Проверяем, что клан существует
            clan = get_clan_by_id(clan_id)
            if not clan:
                embed = create_embed(
                    title="❌ Клан не найден",
                    description=f"Клан с ID {clan_id} не найден.",
                    color=EmbedColors.ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Принудительно обновляем владельца
            conn = get_connection()
            cursor = conn.cursor()
            
            # Прямое обновление
            cursor.execute("""
                UPDATE clans SET owner_id = ? WHERE id = ?
            """, (new_owner_id, clan_id))
            
            rows_affected = cursor.rowcount
            logging.info(f"Принудительно обновлено строк: {rows_affected}")
            
            conn.commit()
            conn.close()
            
            # Проверяем результат
            updated_clan = get_clan_by_id(clan_id)
            if updated_clan and updated_clan['owner_id'] == new_owner_id:
                embed = create_embed(
                    title="✅ Владелец обновлен",
                    description=f"Владелец клана **{clan['name']}** принудительно изменен на <@{new_owner_id}>",
                    color=EmbedColors.SUCCESS
                )
            else:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Не удалось обновить владельца клана.",
                    color=EmbedColors.ERROR
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logging.error(f"Ошибка при принудительном обновлении владельца: {e}")
            embed = create_embed(
                title="❌ Ошибка",
                description=f"Произошла ошибка при обновлении владельца:\n```{str(e)}```",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="clan_change_owner", description="Изменить владельца клана (только для администраторов)")
    @app_commands.describe(clan_id="ID клана", new_owner="Новый владелец клана")
    @app_commands.default_permissions(administrator=True)
    async def clan_change_owner_command(self, interaction: discord.Interaction, clan_id: int, new_owner: discord.Member):
        """Команда для изменения владельца клана"""
        try:
            clan = get_clan_by_id(clan_id)
            if not clan:
                embed = create_embed(
                    title="❌ Клан не найден",
                    description=f"Клан с ID {clan_id} не найден.",
                    color=EmbedColors.ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Проверяем, что новый владелец не состоит в другом клане
            user_clan = get_user_clan(new_owner.id)
            if user_clan and user_clan['id'] != clan_id:
                embed = create_embed(
                    title="❌ Ошибка",
                    description=f"{new_owner.mention} уже состоит в клане **{user_clan['name']}**!",
                    color=EmbedColors.ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Обновляем владельца в базе данных
            conn = get_connection()
            cursor = conn.cursor()
            
            # Проверяем, что клан существует
            cursor.execute("SELECT id, owner_id FROM clans WHERE id = ?", (clan_id,))
            result = cursor.fetchone()
            if not result:
                logging.error(f"Клан {clan_id} не найден в базе данных")
                conn.close()
                return
            
            result_dict = dict(result)
            logging.info(f"Текущий владелец в базе: {result_dict.get('owner_id')}")
            
            # Выполняем обновление
            cursor.execute("""
                UPDATE clans SET owner_id = ? WHERE id = ?
            """, (new_owner.id, clan_id))
            
            # Проверяем количество измененных строк
            rows_affected = cursor.rowcount
            logging.info(f"Обновлено строк: {rows_affected}")
            
            conn.commit()
            conn.close()
            
            # Отладочная информация
            logging.info(f"Владелец клана {clan_id} изменен с {clan['owner_id']} на {new_owner.id}")
            
            # Проверяем, что обновление прошло успешно
            updated_clan = get_clan_by_id(clan_id)
            if updated_clan:
                logging.info(f"Новый владелец в базе: {updated_clan['owner_id']}")
            else:
                logging.error(f"Не удалось получить обновленный клан {clan_id}")
            
            # Удаляем старого владельца из участников
            remove_clan_member(clan_id, clan['owner_id'])
            
            # Добавляем нового владельца как участника
            add_clan_member(clan_id, new_owner.id, 'owner')
            
            # Даем роль клана новому владельцу
            role = interaction.guild.get_role(clan['role_id'])
            if role:
                await new_owner.add_roles(role)
            
            # Убираем роль у старого владельца
            old_owner = interaction.guild.get_member(clan['owner_id'])
            if old_owner and role:
                await old_owner.remove_roles(role)
            
            embed = create_embed(
                title="✅ Владелец изменен",
                description=f"Владелец клана **{clan['name']}** изменен на {new_owner.mention}",
                color=EmbedColors.SUCCESS
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logging.error(f"Ошибка при изменении владельца клана: {e}")
            embed = create_embed(
                title="❌ Ошибка",
                description=f"Произошла ошибка при изменении владельца:\n```{str(e)}```",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="clan_delete", description="Удалить клан (только для администраторов)")
    @app_commands.describe(clan_id="ID клана для удаления")
    @app_commands.default_permissions(administrator=True)
    async def clan_delete_command(self, interaction: discord.Interaction, clan_id: int):
        """Команда для удаления клана"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            clan = get_clan_by_id(clan_id)
            if not clan:
                embed = create_embed(
                    title="❌ Клан не найден",
                    description=f"Клан с ID {clan_id} не найден.",
                    color=EmbedColors.ERROR
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Проверяем права бота
            bot_member = interaction.guild.get_member(self.bot.user.id)
            bot_permissions = interaction.channel.permissions_for(bot_member)
            
            logging.info(f"Права бота для удаления:")
            logging.info(f"- Управление ролями: {bot_permissions.manage_roles}")
            logging.info(f"- Управление каналами: {bot_permissions.manage_channels}")
            logging.info(f"- Удаление каналов: {bot_permissions.manage_channels}")
            
            if not bot_permissions.manage_roles:
                logging.error("У бота нет прав на управление ролями!")
            if not bot_permissions.manage_channels:
                logging.error("У бота нет прав на управление каналами!")
            
            # Получаем всех участников клана
            members = get_clan_members(clan_id)
            logging.info(f"Найдено участников клана: {len(members)}")
            
            # Удаляем роль клана у всех участников
            role = interaction.guild.get_role(clan['role_id'])
            if role:
                logging.info(f"Найдена роль клана: {role.name} (ID: {role.id})")
                
                # Проверяем позицию роли в иерархии
                bot_member = interaction.guild.get_member(self.bot.user.id)
                if bot_member.top_role.position <= role.position:
                    logging.warning(f"Роль клана {role.name} находится выше или на том же уровне, что и роль бота!")
                
                for member_data in members:
                    member = interaction.guild.get_member(member_data['user_id'])
                    if member and role in member.roles:
                        try:
                            await member.remove_roles(role)
                            logging.info(f"Роль клана {clan['name']} удалена у {member.name}")
                        except Exception as e:
                            logging.error(f"Ошибка при удалении роли у {member.name}: {e}")
                
                # Теперь удаляем саму роль
                try:
                    await role.delete()
                    logging.info(f"Роль клана {clan['name']} успешно удалена")
                except Exception as e:
                    logging.error(f"Ошибка при удалении роли клана: {e}")
                    logging.error(f"Детали ошибки: {type(e).__name__}: {str(e)}")
            else:
                logging.warning(f"Роль клана с ID {clan['role_id']} не найдена!")
            
            # Удаляем текстовый канал
            text_channel = interaction.guild.get_channel(clan['text_channel_id'])
            if text_channel:
                logging.info(f"Найден текстовый канал: {text_channel.name} (ID: {text_channel.id})")
                
                # Проверяем права бота для этого канала
                text_permissions = text_channel.permissions_for(bot_member)
                logging.info(f"Права бота для текстового канала: управление каналами = {text_permissions.manage_channels}")
                
                try:
                    await text_channel.delete()
                    logging.info(f"Текстовый канал клана {clan['name']} успешно удален")
                except Exception as e:
                    logging.error(f"Ошибка при удалении текстового канала: {e}")
                    logging.error(f"Детали ошибки: {type(e).__name__}: {str(e)}")
            else:
                logging.warning(f"Текстовый канал с ID {clan['text_channel_id']} не найден!")
            
            # Удаляем основной голосовой канал
            voice_channel = interaction.guild.get_channel(clan['voice_channel_id'])
            if voice_channel:
                logging.info(f"Найден основной голосовой канал: {voice_channel.name} (ID: {voice_channel.id})")
                try:
                    await voice_channel.delete()
                    logging.info(f"Основной голосовой канал клана {clan['name']} успешно удален")
                except Exception as e:
                    logging.error(f"Ошибка при удалении основного голосового канала: {e}")
                    logging.error(f"Детали ошибки: {type(e).__name__}: {str(e)}")
            else:
                logging.warning(f"Основной голосовой канал с ID {clan['voice_channel_id']} не найден!")
            
            # Удаляем дополнительные голосовые каналы
            voice_channels = get_clan_voice_channels(clan_id)
            logging.info(f"Найдено дополнительных голосовых каналов: {len(voice_channels)}")
            for channel_id in voice_channels:
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    logging.info(f"Удаляем дополнительный голосовой канал: {channel.name} (ID: {channel_id})")
                    try:
                        await channel.delete()
                        logging.info(f"Дополнительный голосовой канал {channel_id} успешно удален")
                    except Exception as e:
                        logging.error(f"Ошибка при удалении дополнительного голосового канала {channel_id}: {e}")
                        logging.error(f"Детали ошибки: {type(e).__name__}: {str(e)}")
                else:
                    logging.warning(f"Дополнительный голосовой канал с ID {channel_id} не найден!")
            
            # Деактивируем клан в базе данных
            deactivate_clan(clan_id)
            
            embed = create_embed(
                title="✅ Клан удален",
                description=f"Клан **{clan['name']}** и все связанные роли и каналы удалены.",
                color=EmbedColors.SUCCESS
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logging.error(f"Ошибка при удалении клана: {e}")
            embed = create_embed(
                title="❌ Ошибка",
                description=f"Произошла ошибка при удалении клана:\n```{str(e)}```",
                color=EmbedColors.ERROR
            )
            try:
                await interaction.followup.send(embed=embed, ephemeral=True)
            except:
                await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="clan_fix_db", description="Исправить базу данных кланов (только для администраторов)")
    @app_commands.default_permissions(administrator=True)
    async def clan_fix_db_command(self, interaction: discord.Interaction):
        """Команда для исправления базы данных кланов"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Получаем все кланы
            clans = get_all_clans()
            fixed_count = 0
            
            for clan in clans:
                logging.info(f"Проверяем клан: {clan['name']} (ID: {clan['id']})")
                
                # Проверяем роль
                role = interaction.guild.get_role(clan['role_id'])
                if not role:
                    logging.warning(f"Роль клана {clan['name']} не найдена (ID: {clan['role_id']})")
                
                # Проверяем текстовый канал
                text_channel = interaction.guild.get_channel(clan['text_channel_id'])
                if not text_channel:
                    logging.warning(f"Текстовый канал клана {clan['name']} не найден (ID: {clan['text_channel_id']})")
                
                # Проверяем основной голосовой канал
                voice_channel = interaction.guild.get_channel(clan['voice_channel_id'])
                if not voice_channel:
                    logging.warning(f"Основной голосовой канал клана {clan['name']} не найден (ID: {clan['voice_channel_id']})")
                
                # Проверяем дополнительные голосовые каналы
                voice_channels = get_clan_voice_channels(clan['id'])
                for channel_id in voice_channels:
                    channel = interaction.guild.get_channel(channel_id)
                    if not channel:
                        logging.warning(f"Дополнительный голосовой канал клана {clan['name']} не найден (ID: {channel_id})")
                
                fixed_count += 1
            
            embed = create_embed(
                title="✅ База данных проверена",
                description=f"Проверено кланов: {fixed_count}\n\nПроверьте логи для детальной информации.",
                color=EmbedColors.SUCCESS
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logging.error(f"Ошибка при проверке базы данных: {e}")
            embed = create_embed(
                title="❌ Ошибка",
                description=f"Произошла ошибка при проверке базы данных:\n```{str(e)}```",
                color=EmbedColors.ERROR
            )
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(DeveloperCog(bot))
