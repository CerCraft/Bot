import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
from datetime import timedelta, datetime
import sqlite3
from src.core.config import settings
from src.database.discipline import (
    add_warning,
    remove_one_warning,
    add_strike,
    remove_one_strike,
    add_praise,
    count_warnings,
    count_strikes,
    count_praises,
    cleanup_expired,
    get_history,
)
from src.utils.embed import create_embed, EmbedColors
from src.database.discipline import add_punishment_history


DB_PATH = "src/database/mutes.db"


class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.init_db()
        self.check_mutes.start()
        self.cleanup_discipline.start()

    def init_db(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mutes (
                user_id INTEGER,
                guild_id INTEGER,
                type TEXT,
                end_time REAL,
                PRIMARY KEY (user_id, guild_id, type)
            )
        """)
        # punishments_history теперь хранится в discipline.db
        conn.commit()
        conn.close()

    def log_punishment(self, user_id: int, guild_id: int, moderator_id: int, ptype: str, reason: str):
        # Записываем в discipline.db, чтобы история учитывала все виды наказаний
        add_punishment_history(user_id, guild_id, moderator_id, ptype, reason, datetime.utcnow().timestamp())

    def count_total_punishments(self, user_id: int, guild_id: int) -> int:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM punishments_history WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        )
        result = cursor.fetchone()[0]
        conn.close()
        return result


    def save_mute(self, user_id: int, guild_id: int, mute_type: str, duration: timedelta):
        end_time = (datetime.utcnow() + duration).timestamp()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "REPLACE INTO mutes (user_id, guild_id, type, end_time) VALUES (?, ?, ?, ?)",
            (user_id, guild_id, mute_type, end_time)
        )
        conn.commit()
        conn.close()

    def remove_mute(self, user_id: int, guild_id: int, mute_type: str):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM mutes WHERE user_id = ? AND guild_id = ? AND type = ?",
            (user_id, guild_id, mute_type)
        )
        conn.commit()
        conn.close()

    def get_all_mutes(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, guild_id, type, end_time FROM mutes")
        rows = cursor.fetchall()
        conn.close()
        return rows

    # ========== TASK ==========
    @tasks.loop(minutes=1)
    async def check_mutes(self):
        """Проверяет истёкшие мюты"""
        now = datetime.utcnow().timestamp()
        expired = []

        for user_id, guild_id, mute_type, end_time in self.get_all_mutes():
            if end_time <= now:
                expired.append((user_id, guild_id, mute_type))

        for user_id, guild_id, mute_type in expired:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            member = guild.get_member(user_id)
            if not member:
                continue

            try:
                if mute_type == "text":
                    mute_role = guild.get_role(settings.TEXT_MUTE_ROLE_ID)
                    if mute_role and mute_role in member.roles:
                        await member.remove_roles(mute_role, reason="Истёк срок мута")
                elif mute_type == "voice":
                    mute_role = guild.get_role(settings.VOICE_MUTE_ROLE_ID)
                    if mute_role and mute_role in member.roles:
                        await member.remove_roles(mute_role, reason="Истёк срок мута")
                elif mute_type == "ban":
                    try:
                        await guild.unban(discord.Object(id=user_id), reason="Истёк срок бана")
                    except discord.NotFound:
                        pass
            except Exception as e:
                print(f"⚠️ Ошибка при снятии мута с {member}: {e}")

            self.remove_mute(user_id, guild_id, mute_type)

    @check_mutes.before_loop
    async def before_check_mutes(self):
        await self.bot.wait_until_ready()

    # Очистка просроченных выговоров/страйков
    @tasks.loop(minutes=30)
    async def cleanup_discipline(self):
        cleanup_expired()

    @cleanup_discipline.before_loop
    async def before_cleanup_discipline(self):
        await self.bot.wait_until_ready()

    async def _log_moderation_action(self, guild: discord.Guild, moderator: discord.Member, target: discord.Member, action_type: str, reason: str, duration: str = None):
        if settings.log_channel_moderation_id:
            log_channel = guild.get_channel(settings.log_channel_moderation_id)
            if log_channel and isinstance(log_channel, discord.TextChannel):
                embed = create_embed(
                    title=f"🔔 Модерация: {action_type}",
                    color=EmbedColors.INFO,
                    author=moderator
                )
                embed.set_thumbnail(url=moderator.display_avatar.url)
                embed.add_field(name="Модератор", value=f"{moderator.mention} (`{moderator.id}`)", inline=False)
                embed.add_field(name="Цель", value=f"{target.mention} (`{target.id}`)", inline=False)
                embed.add_field(name="Действие", value=action_type, inline=False)
                if duration:
                    embed.add_field(name="Длительность", value=duration, inline=False)
                embed.add_field(name="Причина", value=reason, inline=False)
                await log_channel.send(embed=embed)

    # ========== COMMANDS ==========
    @app_commands.command(name="clear", description="Очистить сообщения в канале")
    @app_commands.describe(amount="Количество сообщений для удаления")
    async def clear(self, interaction: discord.Interaction, amount: int):
        author_roles = [role.id for role in interaction.user.roles]
        has_access = (
            any(role_id in author_roles for role_id in settings.moderator_command_clear)
            or interaction.user.guild_permissions.administrator
        )

        if not has_access:
            embed = create_embed(
                title="Ошибка доступа",
                description="❌ У вас нет доступа для этой команды!",
                color=EmbedColors.ERROR,
                author=interaction.user
            )
            await interaction.response.send_message(embed=embed, ephemeral=False)
            return

        if amount <= 0:
            embed = create_embed(
                title="Ошибка",
                description="❌ Укажите количество сообщений больше 0!",
                color=EmbedColors.WARNING,
                author=interaction.user
            )
            await interaction.response.send_message(embed=embed, ephemeral=False)
            return

        # Send initial response
        embed = create_embed(
            title="Очистка сообщений",
            description=f"🧹 Удаляю `{amount}` сообщений...",
            color=EmbedColors.INFO,
            author=interaction.user
        )
        await interaction.response.send_message(embed=embed, ephemeral=False)
        
        # Store the bot's message to exclude it from purge
        bot_message = None
        async for message in interaction.channel.history(limit=1):
            if message.author == self.bot.user:
                bot_message = message
                break

        # Purge messages, excluding the bot's own message
        deleted = await interaction.channel.purge(limit=amount, check=lambda m: m != bot_message)

        # Send completion message
        embed = create_embed(
            title="Очистка завершена",
            description=f"🧹 Удалено `{len(deleted)}` сообщений.",
            color=EmbedColors.SUCCESS,
            author=interaction.user
        )
        await interaction.channel.send(embed=embed)
        await self._log_moderation_action(
            interaction.guild,
            interaction.user,
            self.bot.user, 
            "Очистка сообщений",
            f"Удалено {len(deleted)} сообщений в канале {interaction.channel.mention}"
        )

    @app_commands.command(name="moderate", description="Панель модерации пользователя")
    @app_commands.describe(member="Участник для модерации")
    async def moderate(self, interaction: discord.Interaction, member: discord.Member):
        # Проверка доступа
        if not any(role.id in settings.moderator_command_moderate for role in interaction.user.roles):
            from src.utils.embed import create_access_error_embed
            embed = create_access_error_embed(interaction.user)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=False, thinking=True)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # активные наказания
        cursor.execute("SELECT type FROM mutes WHERE user_id = ? AND guild_id = ?", (member.id, interaction.guild.id))
        active_mutes = [row[0] for row in cursor.fetchall()]

        # общее количество наказаний
        cursor.execute("SELECT COUNT(*) FROM punishments_history WHERE user_id = ? AND guild_id = ?", (member.id, interaction.guild.id))
        total_punishments = cursor.fetchone()[0] or 0
        conn.close()

        # роли
        roles = [role.mention for role in member.roles if role.name != "@everyone"]
        roles_text = ", ".join(roles) if roles else "Нет"

        # embed
        embed = create_embed(
            title=f"{member.name}",
            color=EmbedColors.INFO,
            author=interaction.user
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Имя пользователя", value=f"**{member.display_name}** (`{member.id}`)", inline=False)
        embed.add_field(name="Аккаунт создан", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=False)
        embed.add_field(name="Присоединился на сервер", value=f"<t:{int(member.joined_at.timestamp())}:R>", inline=False)
        embed.add_field(name="Количество наказаний ( всего )", value=str(total_punishments), inline=True)
        embed.add_field(name="Текущие роли", value=roles_text, inline=False)

        view = ModerationView(self.bot, target=member, moderator=interaction.user, active_mutes=active_mutes)

        await interaction.followup.send(embed=embed, view=view, ephemeral=False)

    # ========== DISCIPLINE COMMANDS ==========
    @app_commands.command(name="warn", description="Выдать предупреждение пользователю")
    @app_commands.describe(member="Кому выдать предупреждение", reason="Причина")
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        roles = [r.id for r in interaction.user.roles]
        if not (any(r in settings.moderator_command_warn for r in roles) or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("❌ Нет доступа.", ephemeral=False)
            return
        add_warning(member.id, interaction.guild.id, interaction.user.id, reason)
        await interaction.response.send_message(f"✅ {member.mention}: предупреждение выдано.", ephemeral=False)
        await self._log_moderation_action(interaction.guild, interaction.user, member, "Предупреждение (команда)", reason)

    @app_commands.command(name="warn_remove", description="Снять предупреждение у пользователя")
    @app_commands.describe(member="У кого снять предупреждение")
    async def warn_remove(self, interaction: discord.Interaction, member: discord.Member):
        roles = [r.id for r in interaction.user.roles]
        if not (any(r in settings.moderator_command_warn_remove for r in roles) or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("❌ Нет доступа.", ephemeral=False)
            return
        ok = remove_one_warning(member.id, interaction.guild.id)
        if ok:
            await interaction.response.send_message(f"✅ {member.mention}: предупреждение снято.", ephemeral=False)
            await self._log_moderation_action(interaction.guild, interaction.user, member, "Снятие предупреждения (команда)", "Снято 1 предупреждение")
        else:
            await interaction.response.send_message(f"ℹ️ {member.mention}: предупреждений нет.", ephemeral=False)

    @app_commands.command(name="strike", description="Выдать страйк пользователю")
    @app_commands.describe(member="Кому выдать страйк", reason="Причина")
    async def strike(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        roles = [r.id for r in interaction.user.roles]
        if not (any(r in settings.moderator_command_strike for r in roles) or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("❌ Нет доступа.", ephemeral=False)
            return
        add_strike(member.id, interaction.guild.id, interaction.user.id, reason)
        await interaction.response.send_message(f"✅ {member.mention}: страйк выдан.", ephemeral=False)
        await self._log_moderation_action(interaction.guild, interaction.user, member, "Страйк (команда)", reason)

    @app_commands.command(name="praise", description="Выдать похвалу пользователю")
    @app_commands.describe(member="Кому выдать похвалу", reason="За что хвалим")
    async def praise(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        roles = [r.id for r in interaction.user.roles]
        if not (any(r in settings.moderator_command_praise for r in roles) or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("❌ Нет доступа.", ephemeral=False)
            return
        add_praise(member.id, interaction.guild.id, interaction.user.id, reason)
        await interaction.response.send_message(f"✅ {member.mention}: похвала выдана.", ephemeral=False)
        await self._log_moderation_action(interaction.guild, interaction.user, member, "Похвала (команда)", reason)

    @app_commands.command(name="discipline_info", description="Информация о дисциплинарных записях пользователя")
    @app_commands.describe(member="Пользователь")
    async def discipline_info(self, interaction: discord.Interaction, member: discord.Member):
        roles = [r.id for r in interaction.user.roles]
        if not (any(r in settings.moderator_command_discipline_view for r in roles) or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("❌ Нет доступа.", ephemeral=False)
            return
        # cleanup first to avoid showing expired
        cleanup_expired()
        w = count_warnings(member.id, interaction.guild.id)
        s = count_strikes(member.id, interaction.guild.id)
        p = count_praises(member.id, interaction.guild.id)
        embed = create_embed(
            title=f"Дисциплина: {member.display_name}",
            description=(
                f"выговоры `{w}/3`\n" \
                f"страйки `{s}/2`\n" \
                f"похвалы `{p}/3`"
            ),
            color=EmbedColors.INFO,
            author=interaction.user,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=False)

class PunishmentModal(ui.Modal, title="Назначение наказания"):
    reason = ui.TextInput(label="Причина", style=discord.TextStyle.paragraph, required=True)
    duration = ui.TextInput(label="Длительность (10m, 2h, 1d)", required=True)

    def __init__(self, action: str, bot: commands.Bot, target: discord.Member, moderator: discord.Member, message_id: int | None = None):
        super().__init__()
        self.action = action
        self.bot = bot
        self.target = target
        self.moderator = moderator
        self.message_id = message_id

    def parse_duration(self) -> timedelta:
        text = (self.duration.value or "").lower()
        digits = ''.join(filter(str.isdigit, text))
        num = int(digits) if digits else 10
        if "m" in text:
            return timedelta(minutes=num)
        elif "h" in text:
            return timedelta(hours=num)
        elif "d" in text:
            return timedelta(days=num)
        return timedelta(minutes=10)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False, thinking=True)
        duration = self.parse_duration()
        reason = self.reason.value
        cog: ModerationCog = self.bot.get_cog("ModerationCog")

        try:
            if self.action == "mute_text":
                mute_role = interaction.guild.get_role(settings.TEXT_MUTE_ROLE_ID)
                if mute_role:
                    # refresh member to avoid stale roles cache
                    self.target = await interaction.guild.fetch_member(self.target.id)
                    await self.target.add_roles(mute_role, reason=reason)
                    cog.save_mute(self.target.id, interaction.guild.id, "text", duration)
                    cog.log_punishment(self.target.id, interaction.guild.id, self.moderator.id, "text", reason)
                    await cog._log_moderation_action(
                        interaction.guild,
                        self.moderator,
                        self.target,
                        "Текстовый мут",
                        reason,
                        str(duration)
                    )
            elif self.action == "mute_voice":
                mute_role = interaction.guild.get_role(settings.VOICE_MUTE_ROLE_ID)
                if mute_role:
                    self.target = await interaction.guild.fetch_member(self.target.id)
                    await self.target.add_roles(mute_role, reason=reason)
                    cog.save_mute(self.target.id, interaction.guild.id, "voice", duration)
                    cog.log_punishment(self.target.id, interaction.guild.id, self.moderator.id, "voice", reason)
                    await cog._log_moderation_action(
                        interaction.guild,
                        self.moderator,
                        self.target,
                        "Голосовой мут",
                        reason,
                        str(duration)
                    )
            elif self.action == "ban":
                await self.target.ban(reason=reason, delete_message_days=0)
                cog.save_mute(self.target.id, interaction.guild.id, "ban", duration)
                cog.log_punishment(self.target.id, interaction.guild.id, self.moderator.id, "ban", reason)
                await cog._log_moderation_action(
                    interaction.guild,
                    self.moderator,
                    self.target,
                    "Бан",
                    reason,
                    str(duration)
                )

        except Exception as e:
            await interaction.followup.send(
                content=f"❌ Не удалось применить наказание: {e}",
                ephemeral=False
            )
            return

        # Пересобираем данные панели
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT type FROM mutes WHERE user_id = ? AND guild_id = ?", (self.target.id, interaction.guild.id))
        active_mutes = [row[0] for row in cursor.fetchall()]
        conn.close()

        total_punishments = cog.count_total_punishments(self.target.id, interaction.guild.id)

        # refresh member before reading roles for accurate state
        self.target = await interaction.guild.fetch_member(self.target.id)
        roles = [role.mention for role in self.target.roles if role.name != "@everyone"]
        roles_text = ", ".join(roles) if roles else "Нет"

        embed = create_embed(
            title=f"{self.target.name}",
            color=EmbedColors.INFO,
            author=interaction.user
        )
        embed.set_thumbnail(url=self.target.display_avatar.url)
        embed.add_field(name="Имя пользователя", value=f"**{self.target.display_name}** (`{self.target.id}`)", inline=False)
        embed.add_field(name="Аккаунт создан", value=f"<t:{int(self.target.created_at.timestamp())}:R>", inline=False)
        embed.add_field(name="Присоединился на сервер", value=f"<t:{int(self.target.joined_at.timestamp())}:R>", inline=False)
        embed.add_field(name="Количество наказаний (всего)", value=str(total_punishments), inline=False)
        embed.add_field(name="Текущие роли", value=roles_text, inline=False)

        view = ModerationView(self.bot, self.target, self.moderator, active_mutes)

        # Try to edit the original ephemeral panel message; if unavailable, send a new ephemeral message
        message_id = self.message_id
        if not message_id and interaction.message:
            message_id = interaction.message.id
        if message_id:
            await interaction.followup.edit_message(message_id, embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed, view=view, ephemeral=False)

        # Send plain text confirmation
        await interaction.followup.send(
           content="✅ Наказание применено.", ephemeral=False)



class ModerationView(ui.View):
    def __init__(self, bot: commands.Bot, target: discord.Member, moderator: discord.Member, active_mutes: list[str] = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.target = target
        self.moderator = moderator
        self.active_mutes = active_mutes or []

        if self.active_mutes:
            self.add_item(RemovePunishmentButton(bot, target, moderator, self.active_mutes))

        # discipline actions
        self.add_item(WarningButton(bot, target, moderator))
        self.add_item(PraiseButton(bot, target, moderator))
        self.add_item(StrikeButton(bot, target, moderator))
        self.add_item(HistoryButton(bot, target, moderator))

    @ui.button(label="🔇 Мут текст", style=discord.ButtonStyle.secondary)
    async def mute_text_button(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._has_access(interaction):
            return
        message_id = interaction.message.id if interaction.message else None
        await interaction.response.send_modal(PunishmentModal("mute_text", self.bot, self.target, interaction.user, message_id))

    @ui.button(label="🔈 Мут войс", style=discord.ButtonStyle.secondary)
    async def mute_voice_button(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._has_access(interaction):
            return
        message_id = interaction.message.id if interaction.message else None
        await interaction.response.send_modal(PunishmentModal("mute_voice", self.bot, self.target, interaction.user, message_id))
        
    @ui.button(label="🚫 Бан", style=discord.ButtonStyle.secondary)
    async def ban_button(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._has_access(interaction):
            return
        message_id = interaction.message.id if interaction.message else None
        await interaction.response.send_modal(PunishmentModal("ban", self.bot, self.target, interaction.user, message_id))


    async def _has_access(self, interaction: discord.Interaction) -> bool:
        author_roles = [role.id for role in interaction.user.roles]
        has_access = (
            any(role_id in settings.moderator_command_clear for role_id in author_roles)
            or interaction.user.guild_permissions.administrator
        )
        if not has_access:
            await interaction.response.send_message(
                embed=create_embed(
                    title="Ошибка доступа",
                    description="❌ У вас нет прав для модерации!",
                    color=EmbedColors.ERROR,
                    author=interaction.user
                ),
                ephemeral=False
            )
            return False
        return True


class WarningModal(ui.Modal, title="Выдать предупреждение"):
    reason = ui.TextInput(label="Причина", style=discord.TextStyle.paragraph, required=True)

    def __init__(self, bot: commands.Bot, target: discord.Member, moderator: discord.Member):
        super().__init__()
        self.bot = bot
        self.target = target
        self.moderator = moderator

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False, thinking=True)
        add_warning(self.target.id, interaction.guild.id, self.moderator.id, self.reason.value)
        # normalize may add strike; reflect in logs
        await interaction.followup.send(content="✅ Предупреждение выдано.", ephemeral=False)
        cog: ModerationCog = self.bot.get_cog("ModerationCog")
        await cog._log_moderation_action(interaction.guild, self.moderator, self.target, "Предупреждение", self.reason.value)


class PraiseModal(ui.Modal, title="Выдать похвалу"):
    reason = ui.TextInput(label="Причина", style=discord.TextStyle.paragraph, required=True)

    def __init__(self, bot: commands.Bot, target: discord.Member, moderator: discord.Member):
        super().__init__()
        self.bot = bot
        self.target = target
        self.moderator = moderator

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False, thinking=True)
        add_praise(self.target.id, interaction.guild.id, self.moderator.id, self.reason.value)
        await interaction.followup.send(content="✅ Похвала выдана.", ephemeral=False)
        cog: ModerationCog = self.bot.get_cog("ModerationCog")
        await cog._log_moderation_action(interaction.guild, self.moderator, self.target, "Похвала", self.reason.value)


class StrikeModal(ui.Modal, title="Выдать страйк"):
    reason = ui.TextInput(label="Причина", style=discord.TextStyle.paragraph, required=True)

    def __init__(self, bot: commands.Bot, target: discord.Member, moderator: discord.Member):
        super().__init__()
        self.bot = bot
        self.target = target
        self.moderator = moderator

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False, thinking=True)
        add_strike(self.target.id, interaction.guild.id, self.moderator.id, self.reason.value)
        await interaction.followup.send(content="✅ Страйк выдан.", ephemeral=False)
        cog: ModerationCog = self.bot.get_cog("ModerationCog")
        await cog._log_moderation_action(interaction.guild, self.moderator, self.target, "Страйк", self.reason.value)


class WarningButton(ui.Button):
    def __init__(self, bot, target, moderator):
        super().__init__(label="⚠️ Предупреждение", style=discord.ButtonStyle.secondary)
        self.bot = bot
        self.target = target
        self.moderator = moderator

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.moderator:
            await interaction.response.send_message("❌ Только инициатор может использовать это меню.", ephemeral=False)
            return
        await interaction.response.send_modal(WarningModal(self.bot, self.target, self.moderator))


class PraiseButton(ui.Button):
    def __init__(self, bot, target, moderator):
        super().__init__(label="👏 Похвала", style=discord.ButtonStyle.secondary)
        self.bot = bot
        self.target = target
        self.moderator = moderator

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.moderator:
            await interaction.response.send_message("❌ Только инициатор может использовать это меню.", ephemeral=False)
            return
        await interaction.response.send_modal(PraiseModal(self.bot, self.target, self.moderator))


class StrikeButton(ui.Button):
    def __init__(self, bot, target, moderator):
        super().__init__(label="⛔ Страйк", style=discord.ButtonStyle.secondary)
        self.bot = bot
        self.target = target
        self.moderator = moderator

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.moderator:
            await interaction.response.send_message("❌ Только инициатор может использовать это меню.", ephemeral=False)
            return
        await interaction.response.send_modal(StrikeModal(self.bot, self.target, self.moderator))


class HistoryButton(ui.Button):
    def __init__(self, bot, target, moderator):
        super().__init__(label="📜 История взысканий", style=discord.ButtonStyle.secondary)
        self.bot = bot
        self.target = target
        self.moderator = moderator

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.moderator:
            await interaction.response.send_message("❌ Только инициатор может использовать это меню.", ephemeral=False)
            return
        view = HistoryView(self.bot, self.target, self.moderator)
        embed = view.build_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=view)


class HistoryView(ui.View):
    def __init__(self, bot, target, moderator, page: int = 0, page_size: int = 5):
        super().__init__(timeout=None)
        self.bot = bot
        self.target = target
        self.moderator = moderator
        self.page = page
        self.page_size = page_size

    def build_embed(self, guild: discord.Guild) -> discord.Embed:
        offset = self.page * self.page_size
        rows = get_history(self.target.id, guild.id, limit=self.page_size, offset=offset)

        # if empty page but not first, step back one page
        if not rows and self.page > 0:
            self.page -= 1
            offset = self.page * self.page_size
            rows = get_history(self.target.id, guild.id, limit=self.page_size, offset=offset)

        lines = []
        for type_, mod_id, reason, created_at, expire_at in rows:
            mod_text = _format_moderator_with_role(guild, mod_id)
            parts = [
                f"Тип взыскания: {type_}",
                f"Модератор: {mod_text}",
                f"Причина: `{reason if reason else '—'}`",
            ]
            # Показываем срок только для страйков
            if type_ == 'Страйк' and expire_at:
                parts.append(f"Срок: <t:{int(expire_at)}:R>")
            lines.append("\n".join(parts))

        description = "\n\n".join(lines) if lines else "Нет записей."
        embed = create_embed(
            title=f"История взысканий — {self.target.display_name}",
            description=description,
            color=EmbedColors.INFO,
            author=self.moderator,
        )
        embed.set_thumbnail(url=self.target.display_avatar.url)
        return embed

    @ui.button(label="⬅️", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.moderator:
            await interaction.response.send_message("❌ Только инициатор может использовать это меню.", ephemeral=False)
            return
        if self.page > 0:
            self.page -= 1
        embed = self.build_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="➡️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.moderator:
            await interaction.response.send_message("❌ Только инициатор может использовать это меню.", ephemeral=False)
            return
        self.page += 1
        embed = self.build_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

def _format_moderator_with_role(guild: discord.Guild, moderator_id: int) -> str:
    member = guild.get_member(moderator_id)
    if not member:
        return f"<@{moderator_id}>"
    # find highest role from config list
    display_role = None
    for role_id in settings.moderator_display_roles:
        role = guild.get_role(role_id)
        if role and role in member.roles:
            display_role = role
            break
    if display_role:
        return f"{member.mention} ({display_role.mention})"
    return f"{member.mention}"

class RemovePunishmentButton(ui.Button):
    def __init__(self, bot, target, moderator, active_mutes):
        super().__init__(label="⚙️ Снять наказание", style=discord.ButtonStyle.success)
        self.bot = bot
        self.target = target
        self.moderator = moderator
        self.active_mutes = active_mutes

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.moderator:
            await interaction.response.send_message("❌ Только инициатор может использовать это меню.", ephemeral=False)
            return

        view = RemovePunishmentSelectView(self.bot, self.target, self.moderator, self.active_mutes)
        await interaction.response.edit_message(view=view)

class RemovePunishmentSelectView(ui.View):
    def __init__(self, bot, target, moderator, active_mutes):
        super().__init__(timeout=None)
        self.bot = bot
        self.target = target
        self.moderator = moderator
        self.active_mutes = active_mutes

        options = [discord.SelectOption(label="🔙 Назад", value="back")]

        for mtype in active_mutes:
            if mtype == "text":
                options.append(discord.SelectOption(label="Снять мут текста", value="mute_text"))
            elif mtype == "voice":
                options.append(discord.SelectOption(label="Снять мут войса", value="mute_voice"))
            elif mtype == "ban":
                options.append(discord.SelectOption(label="Снять бан", value="ban"))

        self.add_item(RemovePunishmentSelect(bot, target, moderator, options))


class RemovePunishmentSelect(ui.Select):
    def __init__(self, bot, target, moderator, options):
        super().__init__(placeholder="Выберите действие...", options=options)
        self.bot = bot
        self.target = target
        self.moderator = moderator

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False, thinking=True)
        cog: ModerationCog = self.bot.get_cog("ModerationCog")

        if self.values[0] == "back":
            # Обновляем список активных наказаний перед возвратом
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT type FROM mutes WHERE user_id = ? AND guild_id = ?", (self.target.id, interaction.guild.id))
            active_mutes = [row[0] for row in cursor.fetchall()]
            conn.close()

            view = ModerationView(self.bot, self.target, self.moderator, active_mutes)
            await interaction.followup.edit_message(interaction.message.id, view=view)
            return

        mute_type_map = {
            "mute_text": ("text", settings.TEXT_MUTE_ROLE_ID),
            "mute_voice": ("voice", settings.VOICE_MUTE_ROLE_ID),
            "ban": ("ban", None)
        }
        action, role_id = mute_type_map[self.values[0]]

        try:
            if action in ("text", "voice"):
                role = interaction.guild.get_role(role_id)
                if role:
                    # fetch fresh member to avoid stale role cache and try remove regardless of cache state
                    self.target = await interaction.guild.fetch_member(self.target.id)
                    await self.target.remove_roles(role, reason="Снятие наказания модератором")
            elif action == "ban":
                await interaction.guild.unban(discord.Object(id=self.target.id), reason="Снятие наказания модератором")

            cog.remove_mute(self.target.id, interaction.guild.id, action)

            action_type_map = {
                "text": "Снятие текстового мута",
                "voice": "Снятие голосового мута",
                "ban": "Снятие бана",
            }
            action_type_log = action_type_map.get(action, "Неизвестное действие")
            await cog._log_moderation_action(
                interaction.guild,
                self.moderator,
                self.target,
                action_type_log,
                "Снятие наказания модератором"
            )

            # Пересобираем данные
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT type FROM mutes WHERE user_id = ? AND guild_id = ?", (self.target.id, interaction.guild.id))
            active_mutes = [row[0] for row in cursor.fetchall()]
            conn.close()

            total_punishments = cog.count_total_punishments(self.target.id, interaction.guild.id)
            # refresh member to reflect updated roles in UI
            self.target = await interaction.guild.fetch_member(self.target.id)
            roles = [role.mention for role in self.target.roles if role.name != "@everyone"]
            roles_text = ", ".join(roles) if roles else "Нет"

            embed = create_embed(
                title=f"{self.target.name}",
                color=EmbedColors.INFO,
                author=interaction.user
            )
            embed.set_thumbnail(url=self.target.display_avatar.url)
            embed.add_field(name="Имя пользователя", value=f"**{self.target.display_name}** (`{self.target.id}`)", inline=False)
            embed.add_field(name="Аккаунт создан", value=f"<t:{int(self.target.created_at.timestamp())}:R>", inline=False)
            embed.add_field(name="Присоединился на сервер", value=f"<t:{int(self.target.joined_at.timestamp())}:R>", inline=False)
            embed.add_field(name="Количество наказаний (всего)", value=str(total_punishments), inline=False)
            embed.add_field(name="Текущие роли", value=roles_text, inline=False)

            view = ModerationView(self.bot, self.target, self.moderator, active_mutes)

            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)

            # Plain text confirmation
            await interaction.followup.send(
                content="✅ Наказание снято.",
                ephemeral=False
            )

        except Exception as e:
            await interaction.followup.send(
                content="✅ Наказание снято.",
                ephemeral=False
            )




async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
