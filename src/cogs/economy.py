import random
import time
import asyncio
from datetime import datetime, timedelta
import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
from src.utils.embed import create_embed, EmbedColors
from src.core.config import settings
from src.database.economy import (
    init_economy_db,
    get_or_create_account,
    add_cash,
    add_bank,
    transfer_cash_to_bank,
    transfer_bank_to_cash,
    get_cooldowns,
    set_cooldown,
    set_arrest,
    get_rob_stats,
    inc_robbery_stat,
    add_voice_seconds,
    get_top_by_balance,
    get_top_by_level,
    get_top_by_voice,
    get_top_by_robberies,
    get_rank_by_balance,
    get_rank_by_level,
    get_rank_by_voice,
    get_rank_by_robberies,
    get_shop_items,
    purchase_shop_item,
    add_custom_role_request,
    set_request_status,
    get_request,
    add_owned_custom_role,
    get_market_items,
    purchase_market_item,
    get_owned_custom_roles,
    create_role_listing,
    update_role_listing,
    remove_role_listing,
    add_xp,
    set_temp_role,
    get_expired_temp_roles,
    remove_temp_roles,
    cleanup_invalid_listings,
    add_shop_role,
)
from src.database.clans import get_top_clans_by_members
from src.servies import MessageCounterService, ExperienceService


MONEY = getattr(settings, 'ECONOMY_SYMBOL', '💰')


class AmountModal(ui.Modal, title="Введите сумму"):
    amount = ui.TextInput(label="Сумма", required=True, placeholder="1000")

    def __init__(self, action: str, user: discord.Member):
        super().__init__()
        self.action = action
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(str(self.amount.value).strip())
        except ValueError:
            await interaction.response.send_message("❌ Некорректная сумма", ephemeral=False)
            return

        get_or_create_account(interaction.user.id, interaction.guild.id)

        if self.action == 'deposit':
            ok = transfer_cash_to_bank(interaction.user.id, interaction.guild.id, amount)
            if ok:
                # Создаем новый view с обновленным эмбедом
                view = BalanceButtons(interaction.guild, interaction.user, interaction.user)
                updated_embed = view._build_balance_embed()
                await interaction.response.edit_message(embed=updated_embed, view=view)
                await interaction.followup.send("✅ Депозит выполнен.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Недостаточно наличных.", ephemeral=True)
        else:
            ok = transfer_bank_to_cash(interaction.user.id, interaction.guild.id, amount)
            if ok:
                # Создаем новый view с обновленным эмбедом
                view = BalanceButtons(interaction.guild, interaction.user, interaction.user)
                updated_embed = view._build_balance_embed()
                await interaction.response.edit_message(embed=updated_embed, view=view)
                await interaction.followup.send("✅ Снятие выполнено.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Недостаточно средств в банке.", ephemeral=True)


class BalanceButtons(ui.View):
    def __init__(self, guild: discord.Guild, author: discord.Member, target: discord.Member, show_rob_info_only: bool = False):
        super().__init__(timeout=None)
        self.guild = guild
        self.author = author
        self.target = target
        self.show_rob_info_only = show_rob_info_only
        self._update_button_states()
    
    def _update_button_states(self):
        """Обновляет состояние кнопок на основе кулдаунов"""
        try:
            # Если показываем только rob_info, скрываем все остальные кнопки
            if self.show_rob_info_only:
                for child in self.children:
                    if isinstance(child, ui.Button):
                        label = child.label or ""
                        if label != "/rob info":
                            child.disabled = True
                return
            
            # Скрываем кнопку уведомлений для чужих профилей
            if self.target.id != self.author.id:
                for child in self.children:
                    if isinstance(child, ui.Button) and "Уведомления" in (child.label or ""):
                        child.disabled = True
                        break
            else:
                # Обновляем текст кнопки уведомлений для собственного профиля
                for child in self.children:
                    if isinstance(child, ui.Button) and "Уведомления" in (child.label or ""):
                        from src.database.economy import get_notifications_enabled
                        notifications_enabled = get_notifications_enabled(self.target.id, self.guild.id)
                        child.label = "🔕 Уведомления ВЫКЛ" if not notifications_enabled else "🔔 Уведомления ВКЛ"
                        break
            
            cds = get_cooldowns(self.author.id, self.guild.id) or (None, None, None, None, None)
            now = int(time.time())
            daily_cd, work_cd, weekly_cd, _, arrest_until = cds
            for child in self.children:
                if isinstance(child, ui.Button):
                    label = child.label or ""
                    if arrest_until and arrest_until > now:
                        # Only allow rob info while under arrest
                        if label != "/rob info":
                            child.disabled = True
                        continue
                    if label == "/daily" and daily_cd and daily_cd > now:
                        child.disabled = True
                    if label == "/work" and work_cd and work_cd > now:
                        child.disabled = True
                    if label == "/weekly" and weekly_cd and weekly_cd > now:
                        child.disabled = True
        except Exception:
            pass
    
    def _build_balance_embed(self) -> discord.Embed:
        """Создает обновленный эмбед баланса"""
        user = self.target
        acc = get_or_create_account(user.id, self.guild.id)
        cash, bank = acc[0] or 0, acc[1] or 0
        
        # Voice time
        voice_h = int((acc[2] or 0) // 3600)
        voice_m = int(((acc[2] or 0) % 3600) // 60)
        
        # Level and XP
        level = acc[3] or 1
        xp = acc[4] or 0
        
        # Cooldowns
        cds = get_cooldowns(self.author.id, self.guild.id)
        now = int(time.time())
        def cd_label(ts):
            return "доступно" if not ts or ts <= now else f"доступно <t:{int(ts)}:R>"
        daily_label = cd_label(cds[0] if cds else None)
        work_label = cd_label(cds[1] if cds else None)
        weekly_label = cd_label(cds[2] if cds else None)

        # Получаем XP для следующего уровня
        next_level_xp = settings.ECONOMY_XP_PER_LEVEL.get(level, level * 100)
        
        embed = create_embed(
            title=f"Профиль {user.display_name}",
            description=(
                f"**Наличные:** {format_number(cash)}{MONEY}\n"
                f"**В банке:** {format_number(bank)}{MONEY}\n"
                f"**Общий баланс:** {format_number(cash + bank)}{MONEY}"
            ),
            color=discord.Color.from_str("#45248e"),
            author=self.author,
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Время в голосовых каналах", value=f"{voice_h:02d}:{voice_m:02d}", inline=True)
        embed.add_field(name="Опыт", value=f"Уровень {level} `[{xp}/{next_level_xp}]`", inline=True)
        embed.add_field(name="Доступные команды", value=(
            f"- `/daily` - {daily_label}\n"
            f"- `/work` - {work_label}\n"
            f"- `/weekly` - {weekly_label}"
        ), inline=False)
        
        
        return embed

    async def _check_locked(self, interaction: discord.Interaction) -> bool:
        # Arrest blocks actions except viewing balance
        cds = get_cooldowns(interaction.user.id, interaction.guild.id)
        if cds and cds[-1]:
            if cds[-1] and cds[-1] > datetime.utcnow().timestamp():
                await interaction.response.send_message("🚫 Вы под арестом и не можете использовать экономические команды.", ephemeral=False)
                return False
        return True

    @ui.button(label="/daily", style=discord.ButtonStyle.secondary)
    async def daily(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_locked(interaction):
            return
        now = int(time.time())
        daily_amount = getattr(settings, 'ECONOMY_DAILY_AMOUNT', 250)
        get_or_create_account(interaction.user.id, interaction.guild.id)
        cds = get_cooldowns(interaction.user.id, interaction.guild.id)
        next_cd = cds[0] if (cds and len(cds) > 0) else None
        if next_cd and next_cd > now:
            await interaction.response.send_message(f"⌛ Доступно через <t:{int(next_cd)}:R>", ephemeral=True)
            return
        add_bank(interaction.user.id, interaction.guild.id, daily_amount)
        daily_cd_sec = getattr(settings, 'ECONOMY_DAILY_COOLDOWN_SECONDS', 86400)
        next_time = int(time.time() + daily_cd_sec)
        set_cooldown(interaction.user.id, interaction.guild.id, 'daily_cd', next_time)
        
        # Обновляем состояние кнопок и эмбед
        self._update_button_states()
        updated_embed = self._build_balance_embed()
        
        # Создаем эмбед с результатом daily
        daily_embed = create_embed(
            title="🎁 Ежедневная награда",
            description=f"Вы получили ежедневную награду и заработали **{format_number(daily_amount)}{MONEY}**",
            color=discord.Color.from_str("#45248e"),
            author=interaction.user
        )
        
        await interaction.response.edit_message(embed=updated_embed, view=self)
        await interaction.followup.send(embed=daily_embed, ephemeral=True)

    @ui.button(label="/work", style=discord.ButtonStyle.secondary)
    async def work(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_locked(interaction):
            return
        now = int(time.time())
        
        # Получаем список работ из конфига
        jobs = getattr(settings, 'ECONOMY_JOBS', [])
        if not jobs:
            # Fallback на старую систему
            work_amount = getattr(settings, 'ECONOMY_WORK_AMOUNT', 150)
            job_name = "Работа"
            job_description = "Выполнение рабочих обязанностей"
        else:
            # Выбираем случайную работу
            job = random.choice(jobs)
            job_name = job.get('name', 'Работа')
            job_description = job.get('description', 'Выполнение рабочих обязанностей')
            min_reward = job.get('min_reward', 50)
            max_reward = job.get('max_reward', 150)
            work_amount = random.randint(min_reward, max_reward)
        
        # Ensure account exists
        get_or_create_account(interaction.user.id, interaction.guild.id)
        cds = get_cooldowns(interaction.user.id, interaction.guild.id)
        next_cd = cds[1] if (cds and len(cds) > 1) else None
        if next_cd and next_cd > now:
            await interaction.response.send_message(f"⌛ Доступно через <t:{int(next_cd)}:R>", ephemeral=True)
            return
        add_bank(interaction.user.id, interaction.guild.id, work_amount)
        work_cd_sec = getattr(settings, 'ECONOMY_WORK_COOLDOWN_SECONDS', 3600)
        next_time = int(time.time() + work_cd_sec)
        set_cooldown(interaction.user.id, interaction.guild.id, 'work_cd', next_time)
        
        # Обновляем состояние кнопок и эмбед
        self._update_button_states()
        updated_embed = self._build_balance_embed()
        
        # Создаем эмбед с результатом работы
        work_embed = create_embed(
            title="💼 Результат работы",
            description=f"Вы успешно проработали на работе **{job_name}** и заработали **{format_number(work_amount)}{MONEY}**",
            color=discord.Color.from_str("#45248e"),
            author=interaction.user
        )
        
        await interaction.response.edit_message(embed=updated_embed, view=self)
        await interaction.followup.send(embed=work_embed, ephemeral=True)

    @ui.button(label="/weekly", style=discord.ButtonStyle.secondary)
    async def weekly(self, interaction: discord.Interaction, button: ui.Button):
        if not getattr(settings, 'ECONOMY_WEEKLY_ENABLED', True):
            await interaction.response.send_message("❌ Недельная награда отключена.", ephemeral=True)
            return
        if not await self._check_locked(interaction):
            return
        now = int(time.time())
        weekly_amount = getattr(settings, 'ECONOMY_WEEKLY_AMOUNT', 1000)
        get_or_create_account(interaction.user.id, interaction.guild.id)
        cds = get_cooldowns(interaction.user.id, interaction.guild.id)
        next_cd = cds[2] if (cds and len(cds) > 2) else None
        if next_cd and next_cd > now:
            await interaction.response.send_message(f"⌛ Доступно через <t:{int(next_cd)}:R>", ephemeral=True)
            return
        add_bank(interaction.user.id, interaction.guild.id, weekly_amount)
        weekly_cd_sec = getattr(settings, 'ECONOMY_WEEKLY_COOLDOWN_SECONDS', 604800)
        next_time = int(time.time() + weekly_cd_sec)
        set_cooldown(interaction.user.id, interaction.guild.id, 'weekly_cd', next_time)
        
        # Обновляем состояние кнопок и эмбед
        self._update_button_states()
        updated_embed = self._build_balance_embed()
        
        # Создаем эмбед с результатом weekly
        weekly_embed = create_embed(
            title="🏆 Недельная награда",
            description=f"Вы получили недельную награду и заработали **{format_number(weekly_amount)}{MONEY}**",
            color=discord.Color.from_str("#45248e"),
            author=interaction.user
        )
        
        await interaction.response.edit_message(embed=updated_embed, view=self)
        await interaction.followup.send(embed=weekly_embed, ephemeral=True)

    @ui.button(label="/deposit", style=discord.ButtonStyle.secondary)
    async def deposit(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(AmountModal('deposit', interaction.user))

    @ui.button(label="/withdraw", style=discord.ButtonStyle.secondary)
    async def withdraw(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(AmountModal('withdraw', interaction.user))

    @ui.button(label="/rob info", style=discord.ButtonStyle.secondary)
    async def rob_info(self, interaction: discord.Interaction, button: ui.Button):
        # Показываем статистику целевого пользователя, а не того, кто нажал кнопку
        total, success, fail, arrests = get_rob_stats(self.target.id, self.guild.id)
        embed = create_embed(
            title=f"Статистика ограблений {self.target.display_name}",
            description=(
                f"За все время пользователь совершил {total} ограблений:\n"
                f"- {success} успешных\n"
                f"- {fail} неуспешно\n"
                f"- {arrests} арест"
            ),
            color=discord.Color.from_str("#45248e"),
            author=interaction.user,
        )
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @ui.button(label="🔔 Уведомления", style=discord.ButtonStyle.secondary)
    async def toggle_notifications(self, interaction: discord.Interaction, button: ui.Button):
        # Проверяем, что это собственный профиль
        if self.target.id != interaction.user.id:
            await interaction.response.send_message("❌ Вы можете управлять уведомлениями только для своего профиля!", ephemeral=True)
            return
        
        from src.database.economy import get_notifications_enabled, set_notifications_enabled
        
        # Получаем текущий статус
        current_status = get_notifications_enabled(interaction.user.id, interaction.guild.id)
        
        # Переключаем статус
        new_status = not current_status
        set_notifications_enabled(interaction.user.id, interaction.guild.id, new_status)
        
        # Обновляем текст кнопки
        button.label = "🔕 Уведомления ВЫКЛ" if not new_status else "🔔 Уведомления ВКЛ"
        
        # Обновляем основной эмбед баланса
        updated_embed = self._build_balance_embed()
        
        # Обновляем сообщение с новым embed и кнопками
        await interaction.response.edit_message(embed=updated_embed, view=self)
        
        # Создаем отдельный эмбед с информацией об уведомлениях
        status_text = "включены" if new_status else "выключены"
        status_emoji = "🔔" if new_status else "🔕"
        notifications_embed = create_embed(
            title="🔔 Уведомления",
            description=f"{status_emoji} **{status_text.upper()}**\n\nВы {'будете' if new_status else 'не будете'} получать уведомления в ЛС о готовности команд `/daily`, `/work`, `/weekly`.",
            color=discord.Color.from_str("#45248e"),
            author=interaction.user
        )
        
        # Отправляем отдельный эмбед с информацией об уведомлениях
        await interaction.followup.send(embed=notifications_embed, ephemeral=True)

    @ui.button(label="Управление ролями", style=discord.ButtonStyle.secondary)
    async def manage_roles(self, interaction: discord.Interaction, button: ui.Button):
        from src.database.economy import get_owned_custom_roles_with_info
        roles_info = get_owned_custom_roles_with_info(interaction.user.id, interaction.guild.id)
        if not roles_info:
            await interaction.response.send_message("У вас нет купленных кастомных ролей.", ephemeral=False)
            return
        view = RoleManageView(interaction.guild, interaction.user, roles_info, interaction.client)
        await interaction.response.send_message("Выберите роль для управления:", view=view, ephemeral=False)


class ListingModal(ui.Modal, title="Создать/обновить листинг"):
    price = ui.TextInput(label="Цена", required=True, placeholder="1000")
    max_sales = ui.TextInput(label="Макс. продаж (пусто = без ограничений)", required=False)
    description = ui.TextInput(label="Описание роли", required=True, placeholder="Краткое описание роли для покупателей", max_length=200)

    def __init__(self, guild: discord.Guild, role_id: int, seller_id: int, update_callback=None):
        super().__init__()
        self.guild = guild
        self.role_id = role_id
        self.seller_id = seller_id
        self.update_callback = update_callback

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price = int(str(self.price.value).strip())
            max_sales = str(self.max_sales.value).strip()
            max_sales_val = int(max_sales) if max_sales else None
            description = str(self.description.value).strip()
        except ValueError:
            await interaction.response.send_message("❌ Некорректные значения.", ephemeral=False)
            return
        
        create_role_listing(self.guild.id, self.role_id, self.seller_id, price, max_sales_val, description)
        
        # Если есть callback для обновления, вызываем его
        if self.update_callback:
            await self.update_callback(interaction)
        else:
            await interaction.response.send_message("✅ Листинг сохранён.", ephemeral=False)


class RoleManageView(ui.View):
    def __init__(self, guild: discord.Guild, owner: discord.Member, roles_info: list[tuple], bot: commands.Bot = None):
        super().__init__(timeout=None)
        self.guild = guild
        self.owner = owner
        self.roles_info = roles_info  # List of (db_id, role_id, created_at) tuples
        self.bot = bot
        self.selected_role = None
        self.selected_db_id = None
        self.selected_created_at = None
        self._build_components()
    
    async def _update_embed_after_listing(self, interaction: discord.Interaction):
        """Обновляет эмбед после создания листинга"""
        role = self.guild.get_role(self.selected_role)
        if role:
            # Получаем информацию о листинге
            from src.database.economy import get_connection
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT price, description FROM role_listings WHERE role_id=? AND guild_id=?", (self.selected_role, self.guild.id))
            listing = c.fetchone()
            conn.close()
            
            listing_info = ""
            if listing:
                listing_info = f"\n\n**📢 Выставлена на продажу:**\nЦена: **{listing[0]}{MONEY}**\nОписание: **{listing[1]}**"
            
            embed = create_embed(
                title=f"🎭 Управление ролью",
                description=f"**Название:** {role.name}\n**ID в базе:** #{self.selected_db_id}\n**Discord ID:** `{role.id}`\n**Цвет:** {role.color}\n**Создана:** <t:{int(self.selected_created_at)}:F>{listing_info}",
                color=discord.Color.from_str("#45248e"),
                author=interaction.user,
            )
            embed.set_thumbnail(url=self.guild.icon.url if self.guild.icon else None)
            
            # Rebuild components to show unlist button
            self._build_components()
            
            await interaction.response.edit_message(embed=embed, view=self)
    
    def _build_components(self):
        """Build UI components based on current state"""
        self.clear_items()
        
        if not self.selected_role:
            # Show role selection only
            options = []
            for db_id, role_id, created_at in self.roles_info:
                role = self.guild.get_role(role_id)
                if role:
                    options.append(discord.SelectOption(
                        label=role.name, 
                        value=str(role_id)
                    ))
            
            # Create the select component with populated options
            if options:
                select = ui.Select(placeholder="Выберите вашу роль", options=options)
                select.callback = self.select_role_callback
                self.add_item(select)
        else:
            # Show action buttons for selected role
            # Check if role is listed
            from src.database.economy import get_connection
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT price, description FROM role_listings WHERE role_id=? AND guild_id=?", (self.selected_role, self.guild.id))
            listing = c.fetchone()
            conn.close()
            
            list_btn = ui.Button(label="Выставить на продажу", style=discord.ButtonStyle.secondary, row=0)
            list_btn.callback = self.list_role_callback
            self.add_item(list_btn)
            
            # Check if user has admin permissions for edit button
            roles = getattr(settings, 'ECONOMY_REVIEW_ROLES', [])
            # Note: can't check here, will check in callback
            edit_btn = ui.Button(label="Изменить роль", style=discord.ButtonStyle.secondary, row=0)
            edit_btn.callback = self.edit_role_callback
            self.add_item(edit_btn)
            
            if listing:
                unlist_btn = ui.Button(label="Снять с продажи", style=discord.ButtonStyle.secondary, row=0)
                unlist_btn.callback = self.unlist_role_callback
                self.add_item(unlist_btn)

    async def select_role_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("❌ Только владелец может управлять.", ephemeral=False)
            return
        
        if not interaction.data.get('values'):
            await interaction.response.send_message("❌ Нет доступных ролей.", ephemeral=False)
            return
        
        self.selected_role = int(interaction.data['values'][0])
        # Find the corresponding db_id and created_at
        for db_id, role_id, created_at in self.roles_info:
            if role_id == self.selected_role:
                self.selected_db_id = db_id
                self.selected_created_at = created_at
                break
        
        # Show role info with action buttons
        role = self.guild.get_role(self.selected_role)
        if role:
            # Check if role is listed
            from src.database.economy import get_connection
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT price, description FROM role_listings WHERE role_id=? AND guild_id=?", (self.selected_role, self.guild.id))
            listing = c.fetchone()
            conn.close()
            
            listing_info = ""
            if listing:
                listing_info = f"\n\n**📢 Выставлена на продажу:**\nЦена: **{listing[0]}{MONEY}**\nОписание: **{listing[1]}**"
            
            embed = create_embed(
                title=f"🎭 Управление ролью",
                description=f"**Название:** {role.name}\n**ID в базе:** #{self.selected_db_id}\n**Discord ID:** `{role.id}`\n**Цвет:** {role.color}\n**Создана:** <t:{int(self.selected_created_at)}:F>{listing_info}",
                color=discord.Color.from_str("#45248e"),
                author=interaction.user,
            )
            embed.set_thumbnail(url=self.guild.icon.url if self.guild.icon else None)
            
            # Rebuild components to show action buttons
            self._build_components()
            
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("❌ Роль не найдена на сервере.", ephemeral=False)

    async def list_role_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("❌ Только владелец может управлять.", ephemeral=False)
            return
        
        if not self.selected_role:
            await interaction.response.send_message("❌ Сначала выберите роль из списка.", ephemeral=False)
            return
        
        await interaction.response.send_modal(ListingModal(self.guild, self.selected_role, self.owner.id, self._update_embed_after_listing))

    async def unlist_role_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("❌ Только владелец может управлять.", ephemeral=False)
            return
        
        if not self.selected_role:
            await interaction.response.send_message("❌ Сначала выберите роль из списка.", ephemeral=False)
            return
        
        remove_role_listing(self.guild.id, self.selected_role)
        
        # Update embed to remove listing info
        role = self.guild.get_role(self.selected_role)
        if role:
            embed = create_embed(
                title=f"🎭 Управление ролью",
                description=f"**Название:** {role.name}\n**ID в базе:** #{self.selected_db_id}\n**Discord ID:** `{role.id}`\n**Цвет:** {role.color}\n**Создана:** <t:{int(self.selected_created_at)}:F>",
                color=discord.Color.from_str("#45248e"),
                author=interaction.user,
            )
            embed.set_thumbnail(url=self.guild.icon.url if self.guild.icon else None)
            
            # Rebuild components to hide unlist button
            self._build_components()
            
            await interaction.response.edit_message(embed=embed, view=self)

    async def edit_role_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("❌ Только владелец может управлять.", ephemeral=False)
            return
        
        if not self.selected_role:
            await interaction.response.send_message("❌ Сначала выберите роль из списка.", ephemeral=False)
            return
        
        # Use bot instance from view
        if not self.bot:
            await interaction.response.send_message("❌ Ошибка: экземпляр бота недоступен.", ephemeral=True)
            return
        await interaction.response.send_modal(RoleEditModal(self.bot, self.guild, self.selected_role, self.owner.id))


class RoleEditModal(ui.Modal, title="Заявка на изменение роли"):
    name = ui.TextInput(label="Новое название роли", required=True, max_length=100)
    color = ui.TextInput(label="Новый цвет (название или #hex)", required=True, placeholder="#ff0000 или red")

    def __init__(self, bot: commands.Bot, guild: discord.Guild, role_id: int, user_id: int):
        super().__init__()
        self.bot = bot
        self.guild = guild
        self.role_id = role_id
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        from src.database.economy import add_role_edit_request, get_or_create_account, add_bank
        
        role = self.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("❌ Роль не найдена на сервере.", ephemeral=False)
            return
        
        # Check if user has enough money (1000 coins)
        acc = get_or_create_account(interaction.user.id, interaction.guild.id)
        bank = acc[1] or 0
        price = 1000
        
        if bank < price:
            await interaction.response.send_message(f"❌ Недостаточно средств. Нужно: {format_number(price)}{MONEY}, у вас: {format_number(bank)}{MONEY}", ephemeral=True)
            return
        
        # Deduct money
        add_bank(interaction.user.id, interaction.guild.id, -price)
        
        # Create request
        new_name = str(self.name.value).strip()
        new_color = str(self.color.value).strip()
        req_id = add_role_edit_request(interaction.user.id, interaction.guild.id, self.role_id, new_name, new_color)
        
        # Post to review channel
        channel_id = getattr(settings, 'ECONOMY_REVIEW_CHANNEL_ID', None)
        if not channel_id:
            await interaction.response.send_message("❌ Канал ревью не настроен.", ephemeral=False)
            return
        
        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("❌ Канал ревью не найден.", ephemeral=False)
            return
        
        embed = create_embed(
            title="Заявка на изменение роли",
            description=(
                f"Пользователь: {interaction.user.mention} (`{interaction.user.id}`)\n"
                f"Роль: {role.mention} (`{role.id}`)\n"
                f"Новое название: `{new_name}`\n"
                f"Новый цвет: `{new_color}`\n"
                f"Статус: На рассмотрении\n"
                f"Оплачено: {format_number(price)}{MONEY}"
            ),
            color=discord.Color.from_str("#45248e"),
            author=interaction.user,
        )
        view = RoleEditReviewView(self.bot, req_id)
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Заявка отправлена на рассмотрение. Списано: {format_number(price)}{MONEY}", ephemeral=False)


class RoleEditReviewView(ui.View):
    def __init__(self, bot: commands.Bot, req_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.req_id = req_id

    def _is_reviewer(self, member: discord.Member) -> bool:
        if member.guild_permissions.administrator:
            return True
        allowed = getattr(settings, 'ECONOMY_REVIEW_ROLES', [])
        return any(role.id in allowed for role in member.roles)

    @ui.button(label="Одобрить", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: ui.Button):
        from src.database.economy import get_role_edit_request, set_role_edit_request_status
        
        if not self._is_reviewer(interaction.user):
            await interaction.response.send_message("❌ Нет доступа.", ephemeral=False)
            return
        
        row = get_role_edit_request(self.req_id)
        if not row:
            await interaction.response.send_message("❌ Заявка не найдена.", ephemeral=False)
            return
        
        _, user_id, guild_id, role_id, new_name, new_color, status = row
        guild = interaction.guild
        role = guild.get_role(role_id)
        
        if not role:
            await interaction.response.send_message("❌ Роль не найдена на сервере.", ephemeral=False)
            set_role_edit_request_status(self.req_id, 'denied', interaction.user.id)
            return
        
        # Check if name is unique
        if discord.utils.get(guild.roles, name=new_name) and role.name != new_name:
            await interaction.response.send_message("❌ Роль с таким названием уже существует.", ephemeral=False)
            set_role_edit_request_status(self.req_id, 'denied', interaction.user.id)
            try:
                user = guild.get_member(user_id) or await guild.fetch_member(user_id)
                await user.send("❌ Ваша заявка на изменение роли отклонена: роль с таким названием уже существует.")
            except Exception:
                pass
            return
        
        # Update role
        try:
            new_color_parsed = _parse_color(new_color)
            await role.edit(name=new_name, colour=new_color_parsed, reason=f"Заявка одобрена модератором {interaction.user}")
            set_role_edit_request_status(self.req_id, 'approved', interaction.user.id)
            
            # Update embed
            embed = create_embed(
                title="✅ Заявка на изменение роли - ОДОБРЕНА",
                description=(
                    f"Пользователь: <@{user_id}> (`{user_id}`)\n"
                    f"Роль: {role.mention} (`{role.id}`)\n"
                    f"Новое название: `{new_name}`\n"
                    f"Новый цвет: `{new_color}`\n"
                    f"Статус: **Одобрено**\n"
                    f"Модератор: {interaction.user.mention}"
                ),
                color=discord.Color.from_str("#45248e"),
            )
            
            # Disable buttons
            for item in self.children:
                item.disabled = True
            
            await interaction.response.edit_message(embed=embed, view=self)
            
            # Send DM notification
            try:
                user = guild.get_member(user_id) or await guild.fetch_member(user_id)
                dm_embed = create_embed(
                    title="🎉 Заявка на изменение роли одобрена!",
                    description=(
                        f"Ваша заявка на изменение роли была **одобрена**!\n\n"
                        f"**Информация:**\n"
                        f"• Роль: {role.name}\n"
                        f"• Новое название: `{new_name}`\n"
                        f"• Новый цвет: `{new_color}`\n"
                        f"• Модератор: {interaction.user.display_name}"
                    ),
                    color=discord.Color.from_str("#45248e"),
                )
                await user.send(embed=dm_embed)
            except Exception:
                pass
        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка при изменении роли: {e}", ephemeral=False)

    @ui.button(label="Отклонить", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: ui.Button):
        from src.database.economy import get_role_edit_request, set_role_edit_request_status, add_bank
        
        if not self._is_reviewer(interaction.user):
            await interaction.response.send_message("❌ Нет доступа.", ephemeral=False)
            return
        
        row = get_role_edit_request(self.req_id)
        if not row:
            await interaction.response.send_message("❌ Заявка не найдена.", ephemeral=False)
            return
        
        _, user_id, guild_id, role_id, new_name, new_color, status = row
        guild = interaction.guild
        role = guild.get_role(role_id)
        
        set_role_edit_request_status(self.req_id, 'denied', interaction.user.id)
        
        # Refund money
        add_bank(user_id, guild_id, 1000)
        
        # Update embed
        embed = create_embed(
            title="❌ Заявка на изменение роли - ОТКЛОНЕНА",
            description=(
                f"Пользователь: <@{user_id}> (`{user_id}`)\n"
                f"Роль: {role.mention if role else 'Удалена'} (`{role_id}`)\n"
                f"Новое название: `{new_name}`\n"
                f"Новый цвет: `{new_color}`\n"
                f"Статус: **Отклонено**\n"
                f"Модератор: {interaction.user.mention}\n"
                f"Возврат средств: 1000{MONEY}"
            ),
            color=discord.Color.from_str("#45248e"),
        )
        
        # Disable buttons
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Send DM notification
        try:
            user = guild.get_member(user_id) or await guild.fetch_member(user_id)
            dm_embed = create_embed(
                title="❌ Заявка на изменение роли отклонена",
                description=(
                    f"К сожалению, ваша заявка на изменение роли была **отклонена**.\n\n"
                    f"**Информация:**\n"
                    f"• Роль: {role.name if role else 'Удалена'}\n"
                    f"• Модератор: {interaction.user.display_name}\n"
                    f"• Возврат средств: 1000{MONEY}"
                ),
                color=discord.Color.from_str("#45248e"),
            )
            await user.send(embed=dm_embed)
        except Exception:
            pass


class EconomyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        init_economy_db()
        # Track joined timestamps for voice to accumulate time
        self._voice_joined_ts: dict[tuple[int, int], float] = {}
        self._temp_roles_cleanup.start()

    # Track voice time
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        key = (member.guild.id, member.id)
        now = int(time.time())
        # Joined voice
        if (not before.channel) and after.channel:
            self._voice_joined_ts[key] = now
            return
        # Left voice
        if before.channel and (not after.channel):
            start = self._voice_joined_ts.pop(key, None)
            if start:
                voice_seconds = int(now - start)
                add_voice_seconds(member.id, member.guild.id, voice_seconds)
                # Add XP for voice time
                ExperienceService.add_xp_from_voice(member.id, member.guild.id, voice_seconds / 60)
            return
        # Switched between channels
        if before.channel and after.channel and before.channel.id != after.channel.id:
            start = self._voice_joined_ts.get(key)
            if start:
                voice_seconds = int(now - start)
                add_voice_seconds(member.id, member.guild.id, voice_seconds)
                # Add XP for voice time
                ExperienceService.add_xp_from_voice(member.id, member.guild.id, voice_seconds / 60)
            self._voice_joined_ts[key] = now

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # simple xp per message (anti-spam not implemented here)
        if message.guild and not message.author.bot:
            # Use new experience service
            ExperienceService.add_xp_from_message(message.author.id, message.guild.id)
            # Increment message counter using service
            MessageCounterService.increment_message_count(message.author.id, message.guild.id)

    @tasks.loop(minutes=10)
    async def _temp_roles_cleanup(self):
        now_ts = datetime.utcnow().timestamp()
        for guild in self.bot.guilds:
            expired = get_expired_temp_roles(guild.id, now_ts)
            for user_id, role_ids in expired:
                member = guild.get_member(user_id)
                if not member:
                    continue
                roles = [guild.get_role(rid) for rid in role_ids]
                roles = [r for r in roles if r and r in member.roles]
                if roles:
                    try:
                        await member.remove_roles(*roles, reason="Срок временной роли истёк")
                    except Exception:
                        pass
                remove_temp_roles(user_id, guild.id, role_ids)

    @_temp_roles_cleanup.before_loop
    async def _before_cleanup(self):
        await self.bot.wait_until_ready()


    @app_commands.command(name="balance", description="Профиль экономики пользователя")
    @app_commands.describe(member="Пользователь (необязательно)")
    async def balance(self, interaction: discord.Interaction, member: discord.Member | None = None):
        user = member or interaction.user
        row = get_or_create_account(user.id, interaction.guild.id)
        cash, bank, xp, level, voice_seconds, *_ = row
        voice_h = int(voice_seconds // 3600) if voice_seconds else 0
        voice_m = int((voice_seconds % 3600) // 60) if voice_seconds else 0

        # Получаем XP для следующего уровня
        next_level_xp = settings.ECONOMY_XP_PER_LEVEL.get(level, level * 100)
        
        embed = create_embed(
            title=f"Профиль {user.display_name}",
            description=(
                f"**Наличные:** {format_number(cash)}{MONEY}\n"
                f"**В банке:** {format_number(bank)}{MONEY}\n"
                f"**Общий баланс:** {format_number(cash + bank)}{MONEY}"
            ),
            color=discord.Color.from_str("#45248e"),
            author=interaction.user,
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Время в голосовых каналах", value=f"{voice_h:02d}:{voice_m:02d}", inline=True)
        embed.add_field(name="Опыт", value=f"Уровень {level} `[{xp}/{next_level_xp}]`", inline=True)
        
        # Если команда вызвана на другого пользователя, показываем только информацию об ограблениях
        if member and member.id != interaction.user.id:
            # Получаем статистику ограблений для целевого пользователя
            total, success, fail, arrests = get_rob_stats(user.id, interaction.guild.id)
            embed.add_field(name="Статистика ограблений", value=(
                f"**Всего ограблений:** {total}\n"
                f"**Успешных:** {success}\n"
                f"**Неудачных:** {fail}\n"
                f"**Арестов:** {arrests}"
            ), inline=False)
            
            # Для чужих профилей не показываем никаких кнопок
            await interaction.response.send_message(embed=embed, ephemeral=False)
        else:
            # Обычная логика для собственного профиля
            cds = get_cooldowns(interaction.user.id, interaction.guild.id)
            now = int(time.time())
            def cd_label(ts):
                return "доступно" if not ts or ts <= now else f"доступно <t:{int(ts)}:R>"
            daily_label = cd_label(cds[0] if cds else None)
            work_label = cd_label(cds[1] if cds else None)
            weekly_label = cd_label(cds[2] if cds else None)
            
            embed.add_field(name="Доступные команды", value=(
                f"- `/daily` - {daily_label}\n"
                f"- `/work` - {work_label}\n"
                f"- `/weekly` - {weekly_label}"
            ), inline=False)
            
            view = BalanceButtons(interaction.guild, interaction.user, user)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

    @app_commands.command(name="shop", description="Магазин предметов Naeratus")
    async def shop(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False, thinking=True)
        
        # Очищаем недействительные листинги перед показом магазина
        valid_role_owners = {}
        for member in interaction.guild.members:
            if not member.bot:
                valid_role_owners[member.id] = [role.id for role in member.roles]
        
        cleanup_invalid_listings(interaction.guild.id, valid_role_owners)
        
        view = ShopView(interaction.guild, interaction.user)
        embed = view.build_embed()
        await interaction.followup.send(embed=embed, view=view, ephemeral=False)

    @app_commands.command(name="rob", description="Ограбить пользователя (только наличные)")
    @app_commands.describe(member="Кого ограбить")
    async def rob(self, interaction: discord.Interaction, member: discord.Member):
        if member.id == interaction.user.id:
            embed = create_embed(
                title="❌ Ошибка",
                description="Вы не можете ограбить самого себя!",
                color=discord.Color.from_str("#45248e"),
                author=interaction.user
            )
            await interaction.response.send_message(embed=embed, ephemeral=False)
            return
        
        if member.bot:
            embed = create_embed(
                title="❌ Ошибка",
                description="Ботов нельзя грабить!",
                color=discord.Color.from_str("#45248e"),
                author=interaction.user
            )
            await interaction.response.send_message(embed=embed, ephemeral=False)
            return
        
        # check arrest
        cds = get_cooldowns(interaction.user.id, interaction.guild.id)
        now = int(time.time())
        if cds and len(cds) > 4 and cds[4] and cds[4] > now:
            arrest_time = int(cds[4])
            embed = create_embed(
                title="🚫 Арест",
                description=f"Вы находитесь под арестом!\nОсвобождение: <t:{arrest_time}:R>",
                color=discord.Color.from_str("#45248e"),
                author=interaction.user
            )
            await interaction.response.send_message(embed=embed, ephemeral=False)
            return
        
        # rob cooldown
        rob_cd = cds[3] if (cds and len(cds) > 3) else None
        if rob_cd and rob_cd > now:
            embed = create_embed(
                title="⏰ Кулдаун",
                description=f"Следующее ограбление доступно <t:{int(rob_cd)}:R>",
                color=discord.Color.from_str("#45248e"),
                author=interaction.user
            )
            await interaction.response.send_message(embed=embed, ephemeral=False)
            return

        # success 40%
        success_chance = 0.4
        success = random.random() < success_chance
        
        # compute loot from target cash up to 30%
        target_row = get_or_create_account(member.id, interaction.guild.id)
        target_cash = target_row[0] or 0
        
        # Проверяем минимальное количество денег у жертвы
        min_rob = getattr(settings, 'ECONOMY_ROB_MIN_AMOUNT', 300)
        if target_cash < min_rob:
            embed = create_embed(
                title="❌ Недостаточно средств",
                description=f"У {member.mention} слишком мало наличных для ограбления (минимум: {min_rob}{MONEY})",
                color=discord.Color.from_str("#45248e"),
                author=interaction.user
            )
            await interaction.response.send_message(embed=embed, ephemeral=False)
            return
        
        # Используем настройки из конфига для расчета суммы ограбления
        min_rob = getattr(settings, 'ECONOMY_ROB_MIN_AMOUNT', 300)
        max_rob = getattr(settings, 'ECONOMY_ROB_MAX_AMOUNT', 3500)
        
        if success:
            # Случайная сумма в пределах настроек, но не больше чем есть у жертвы
            loot = random.randint(min_rob, min(max_rob, target_cash))
        else:
            loot = 0
        
        # Varied success messages
        success_messages = [
            f"🎭 Вы незаметно проникли к {member.mention} и украли наличные!",
            f"🦹 Ловкие руки сделали своё дело! {member.mention} и не заметил пропажи!",
            f"🎯 Идеальное ограбление! {member.mention} остался ни с чем!",
            f"🌙 Под покровом ночи вы украли деньги у {member.mention}!",
        ]
        
        # Varied fail messages
        fail_messages = [
            f"😰 {member.mention} заметил вас и успел спрятать деньги!",
            f"🚨 Охрана {member.mention} оказалась на чеку!",
            f"❌ Неудача! {member.mention} был готов к нападению!",
            f"⚠️ План провалился! {member.mention} перехитрил вас!",
        ]
        
        # Arrest messages  
        arrest_messages = [
            "🚓 Полиция уже здесь! Вы арестованы на 6 часов!",
            "👮 Вас поймали с поличным! 6 часов в тюрьме!",
            "🚔 Сирены полиции! Вы отправляетесь за решётку на 6 часов!",
            "⛓️ Наручники защёлкнулись! 6 часов ареста!",
        ]

        if success and loot > 0:
            # transfer cash
            add_cash(member.id, interaction.guild.id, -loot)
            add_cash(interaction.user.id, interaction.guild.id, loot)
            inc_robbery_stat(interaction.user.id, interaction.guild.id, success=True)
            next_rob = int(time.time() + 300)  # 5 минут
            set_cooldown(interaction.user.id, interaction.guild.id, 'rob_cd', next_rob)
            
            embed = create_embed(
                title="✅ Успешное ограбление!",
                description=random.choice(success_messages),
                color=discord.Color.from_str("#45248e"),
                author=interaction.user
            )
            embed.add_field(name="💰 Украдено", value=f"**{loot}{MONEY}**", inline=True)
            embed.add_field(name="🎯 Жертва", value=member.mention, inline=True)
            embed.add_field(name="⏰ След. попытка", value=f"<t:{next_rob}:R>", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=False)
        else:
            # fail; 50/50 arrested
            arrested = random.random() < 0.5
            inc_robbery_stat(interaction.user.id, interaction.guild.id, success=False, arrest=arrested)
            
            if arrested:
                until = int(time.time() + 21600)  # 6 часов
                set_arrest(interaction.user.id, interaction.guild.id, until)
                
                embed = create_embed(
                    title="🚨 Арест!",
                    description=random.choice(fail_messages) + "\n\n" + random.choice(arrest_messages),
                    color=discord.Color.from_str("#45248e"),
                    author=interaction.user
                )
                embed.add_field(name="⛓️ Срок ареста", value="6 часов", inline=True)
                embed.add_field(name="🔓 Освобождение", value=f"<t:{until}:R>", inline=True)
                embed.set_footer(text="Во время ареста экономические команды недоступны")
                await interaction.response.send_message(embed=embed, ephemeral=False)
            else:
                next_rob = int(time.time() + 300)  # 5 минут
                set_cooldown(interaction.user.id, interaction.guild.id, 'rob_cd', next_rob)
                
                embed = create_embed(
                    title="❌ Ограбление провалилось",
                    description=random.choice(fail_messages) + "\n\nВам удалось скрыться!",
                    color=discord.Color.from_str("#45248e"),
                    author=interaction.user
                )
                embed.add_field(name="⏰ След. попытка", value=f"<t:{next_rob}:R>", inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=False)
    
    @app_commands.command(name="unarrest", description="Снять арест с пользователя")
    @app_commands.describe(member="С кого снять арест")
    async def unarrest(self, interaction: discord.Interaction, member: discord.Member):
        roles = getattr(settings, 'ECONOMY_ADMIN_ROLES', [])
        if not (interaction.user.guild_permissions.administrator or any(r.id in roles for r in interaction.user.roles)):
            await interaction.response.send_message("❌ Нет доступа.", ephemeral=False)
            return
        
        # Remove arrest
        set_arrest(member.id, interaction.guild.id, None)
        
        embed = create_embed(
            title="🔓 Арест снят",
            description=f"Пользователь {member.mention} освобождён из-под ареста",
            color=discord.Color.from_str("#45248e"),
            author=interaction.user
        )
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(name="buy_custom_role", description="Создание кастомной роли")
    async def buy_custom_role(self, interaction: discord.Interaction):
        price = getattr(settings, 'ECONOMY_CUSTOM_ROLE_PRICE', 5000)
        monthly = getattr(settings, 'ECONOMY_CUSTOM_ROLE_MONTHLY_PRICE', 2000)
        embed = create_embed(
            title="Создание роли",
            description=(
                f"Условия:\n- Цена: {price}{MONEY}\n- Ежемесячная оплата: {monthly}{MONEY}"
            ),
            color=discord.Color.from_str("#45248e"),
            author=interaction.user,
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        view = CustomRoleStartView(self.bot)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

    @app_commands.command(name="top", description="Топ по балансу/уровню/войсу/кланам")
    async def top(self, interaction: discord.Interaction):
        guild = interaction.guild
        view = TopView(guild, interaction.user)
        embed = await view.build_embed(metric="balance")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

    @app_commands.command(name="coinflip", description="Орел или решка")
    @app_commands.describe(bet="Ставка из банка (50-1000)")
    async def coinflip(self, interaction: discord.Interaction, bet: int):
        if bet < 50 or bet > 1000:
            await interaction.response.send_message("❌ Ставка должна быть от 50 до 1000.", ephemeral=False)
            return
        # arrest check
        cds = get_cooldowns(interaction.user.id, interaction.guild.id)
        now = int(time.time())
        if cds and cds[-1] and cds[-1] > now:
            await interaction.response.send_message("🚫 Вы под арестом.", ephemeral=False)
            return
        # funds
        acc = get_or_create_account(interaction.user.id, interaction.guild.id)
        bank = acc[1] or 0
        if bank < bet:
            await interaction.response.send_message("❌ Недостаточно средств в банке.", ephemeral=True)
            return
        
        # Show choice view
        view = CoinflipView(interaction.user, interaction.guild.id, bet)
        embed = discord.Embed(
            title="🪙 Выберите сторону",
            description=f"Ставка: **{bet}{MONEY}**\n\nВыберите на что ставите:",
            color=discord.Color.from_str("#45248e")
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)


    @app_commands.command(name="blackjack", description="Блекджек против дилера")
    @app_commands.describe(bet="Ставка из банка (минимум 100)")
    async def blackjack(self, interaction: discord.Interaction, bet: int):
        if bet < 100:
            await interaction.response.send_message(f"❌ Минимальная ставка: 100{MONEY}", ephemeral=False)
            return
        
        # Check if user already has active game
        if hasattr(self, '_active_blackjack_games'):
            if interaction.user.id in self._active_blackjack_games:
                await interaction.response.send_message("❌ У вас уже есть активная игра в блекджек!", ephemeral=False)
                return
        else:
            self._active_blackjack_games = set()
        
        cds = get_cooldowns(interaction.user.id, interaction.guild.id)
        now = datetime.utcnow().timestamp()
        if cds and cds[-1] and cds[-1] > now:
            await interaction.response.send_message("🚫 Вы под арестом.", ephemeral=False)
            return
        
        acc = get_or_create_account(interaction.user.id, interaction.guild.id)
        bank = acc[1] or 0
        if bank < bet:
            await interaction.response.send_message("❌ Недостаточно средств в банке.", ephemeral=True)
            return
        
        # Mark game as active
        self._active_blackjack_games.add(interaction.user.id)
        
        view = BlackjackView(interaction.user, interaction.guild.id, bet, self)
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)
        
        # Store message reference for timeout handling
        message = await interaction.original_response()
        view.message = message

    @app_commands.command(name="admin_balance", description="Админ-панель экономики")
    @app_commands.describe(member="Пользователь для управления")
    async def admin_balance(self, interaction: discord.Interaction, member: discord.Member):
        roles = getattr(settings, 'ECONOMY_ADMIN_ROLES', [])
        if not (interaction.user.guild_permissions.administrator or any(r.id in roles for r in interaction.user.roles)):
            await interaction.response.send_message("❌ Нет доступа.", ephemeral=False)
            return
        
        view = AdminBalanceView(interaction.guild, member)
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

    @app_commands.command(name="admin_role_shop", description="Добавить роль в магазин (админ)")
    @app_commands.describe(role="Роль для добавления в магазин (тег или ID)")
    async def admin_role_shop(self, interaction: discord.Interaction, role: str):
        roles = getattr(settings, 'ECONOMY_ADMIN_ROLES', [])
        if not (interaction.user.guild_permissions.administrator or any(r.id in roles for r in interaction.user.roles)):
            await interaction.response.send_message("❌ Нет доступа.", ephemeral=False)
            return
        
        # Парсим роль из строки (может быть тег @role или ID)
        role_id = None
        role_obj = None
        
        # Пробуем найти роль по тегу
        if role.startswith('<@&') and role.endswith('>'):
            role_id = int(role[3:-1])
        else:
            # Пробуем найти по ID
            try:
                role_id = int(role)
            except ValueError:
                # Пробуем найти по имени
                role_obj = discord.utils.get(interaction.guild.roles, name=role)
                if role_obj:
                    role_id = role_obj.id
        
        # Если не нашли по ID, пробуем получить объект роли
        if not role_obj and role_id:
            role_obj = interaction.guild.get_role(role_id)
        
        if not role_obj:
            await interaction.response.send_message("❌ Роль не найдена. Укажите корректный тег роли (@role), ID или название.", ephemeral=True)
            return
        
        # Проверяем, что роль не является @everyone
        if role_obj.is_default():
            await interaction.response.send_message("❌ Нельзя добавить роль @everyone в магазин.", ephemeral=True)
            return
        
        # Проверяем, что роль не является ботом
        if role_obj.managed:
            await interaction.response.send_message("❌ Нельзя добавить управляемую роль (бот, интеграция) в магазин.", ephemeral=True)
            return
        
        # Открываем модальное окно
        await interaction.response.send_modal(AdminShopRoleModal(interaction.guild, role_obj.id))

    @app_commands.command(name="cases", description="Открыть кейсы")
    async def cases(self, interaction: discord.Interaction):
        cases_list = getattr(settings, 'ECONOMY_CASES', [])
        if not cases_list:
            await interaction.response.send_message("❌ Кейсы не настроены.", ephemeral=False)
            return
        
        view = CasesView(interaction.guild, interaction.user, cases_list)
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)


class CasesView(ui.View):
    def __init__(self, guild: discord.Guild, requester: discord.Member, cases_list: list):
        super().__init__(timeout=None)
        self.guild = guild
        self.requester = requester
        self.cases_list = cases_list

    def build_embed(self) -> discord.Embed:
        lines = []
        for idx, case in enumerate(self.cases_list, start=1):
            name = case.get('name', f'Кейс #{idx}')
            price = case.get('price', 0)
            description = case.get('description', 'Описание отсутствует')
            lines.append(f"**{idx}. {name}** Стоимость: {price}{MONEY}\n{description}")
        
        embed = create_embed(
            title="📦 Кейсы Naeratus",
            description="Выберите кейс из списка ниже:\n\n" + "\n\n".join(lines),
            color=discord.Color.from_str("#45248e"),
            author=self.requester,
        )
        embed.set_thumbnail(url=self.guild.icon.url if self.guild.icon else None)
        
        # Update select options
        options = []
        for idx, case in enumerate(self.cases_list):
            name = case.get('name', f'Кейс #{idx+1}')
            options.append(discord.SelectOption(
                label=name,
                value=str(idx),
                emoji="📦"
            ))
        
        for child in self.children:
            if isinstance(child, ui.Select):
                child.options = options
        
        return embed

    @ui.select(placeholder="Выберите кейс для открытия")
    async def select_case(self, interaction: discord.Interaction, select: ui.Select):
        case_idx = int(select.values[0])
        case = self.cases_list[case_idx]
        
        name = case.get('name', f'Кейс #{case_idx+1}')
        price = int(case.get('price', 0))
        rewards = case.get('rewards', [])
        
        # Check funds
        acc = get_or_create_account(interaction.user.id, interaction.guild.id)
        bank = acc[1] or 0
        if bank < price:
            await interaction.response.send_message(f"❌ Недостаточно средств. Нужно: {format_number(price)}{MONEY}, у вас: {format_number(bank)}{MONEY}", ephemeral=True)
            return
        
        # Charge
        add_bank(interaction.user.id, interaction.guild.id, -price)
        
        # Weighted choice
        if not rewards:
            await interaction.response.send_message("❌ В кейсе нет наград", ephemeral=False)
            return
        
        weights = [int(r.get('chance', 1)) for r in rewards]
        reward = random.choices(rewards, weights=weights, k=1)[0]
        
        # Анимация открытия кейса
        animation_embed = create_embed(
            title="📦 Открытие кейса...",
            description="Кейс открывается...",
            color=discord.Color.from_str("#45248e"),
            author=interaction.user
        )
        await interaction.response.edit_message(embed=animation_embed, view=None)
        
        # Анимация (3 кадра)
        animation_frames = [
            "📦 Кейс открывается...",
            "✨ Светящиеся частицы...", 
            "🎁 Награда появляется..."
        ]
        
        message = await interaction.original_response()
        for frame in animation_frames:
            animation_embed.description = frame
            await message.edit(embed=animation_embed)
            await asyncio.sleep(0.8)
        
        # Process reward
        rtype = reward.get('type')
        embed = create_embed(
            title=f"📦 {name}",
            description=f"**Стоимость:** {format_number(price)}{MONEY}",
            color=discord.Color.from_str("#45248e"),
            author=interaction.user,
        )
        
        rarity = reward.get('rarity', 'Обычная')
        
        if rtype == 'money':
            amount = int(reward.get('amount', 0))
            add_bank(interaction.user.id, interaction.guild.id, amount)
            reward_name = reward.get('name', 'Деньги')
            embed.add_field(name="Награда", value=f"{reward_name}: **{amount}{MONEY}**\n**Редкость:** {rarity}", inline=False)
        elif rtype == 'xp':
            amount = int(reward.get('xp', 0))
            add_xp(interaction.user.id, interaction.guild.id, amount)
            reward_name = reward.get('name', 'Опыт')
            embed.add_field(name="Награда", value=f"{reward_name}: **{amount} XP**\n**Редкость:** {rarity}", inline=False)
        elif rtype == 'role':
            role_id = int(reward.get('role_id'))
            duration = int(reward.get('duration_seconds', 0))
            role = interaction.guild.get_role(role_id)
            reward_name = reward.get('name', 'Роль')
            
            if role:
                try:
                    await interaction.user.add_roles(role, reason=f"Награда из кейса {name}")
                    if duration > 0:
                        set_temp_role(interaction.user.id, interaction.guild.id, role.id, datetime.utcnow().timestamp() + duration)
                        embed.add_field(name="Награда", value=f"{reward_name}: {role.mention}\n⏱️ Временная ({duration//3600}ч)\n**Редкость:** {rarity}", inline=False)
                    else:
                        embed.add_field(name="Награда", value=f"{reward_name}: {role.mention}\n♾️ Постоянная\n**Редкость:** {rarity}", inline=False)
                except Exception as e:
                    embed.add_field(name="⚠️ Ошибка", value=f"Не удалось выдать роль: {e}", inline=False)
            else:
                embed.add_field(name="⚠️ Ошибка", value="Роль не найдена на сервере", inline=False)
        else:
            reward_name = reward.get('name', 'Неизвестная награда')
            embed.add_field(name="Награда", value=f"{reward_name}\n**Редкость:** {rarity}", inline=False)
        
        # Создаем новое view с кнопкой "Открыть еще один кейс"
        replay_view = CasesReplayView(self.guild, self.requester, self.cases_list, case_idx)
        await message.edit(embed=embed, view=replay_view)


class CasesReplayView(ui.View):
    def __init__(self, guild: discord.Guild, requester: discord.Member, cases_list: list, case_idx: int):
        super().__init__(timeout=60)
        self.guild = guild
        self.requester = requester
        self.cases_list = cases_list
        self.case_idx = case_idx

    @ui.button(label="📦 Открыть еще один кейс", style=discord.ButtonStyle.primary)
    async def open_another_case(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.requester:
            await interaction.response.send_message("❌ Это не ваш кейс!", ephemeral=True)
            return
        
        # Получаем тот же кейс
        case = self.cases_list[self.case_idx]
        name = case.get('name', f'Кейс #{self.case_idx+1}')
        price = int(case.get('price', 0))
        rewards = case.get('rewards', [])
        
        # Проверяем баланс
        acc = get_or_create_account(interaction.user.id, interaction.guild.id)
        bank = acc[1] or 0
        if bank < price:
            await interaction.response.send_message(f"❌ Недостаточно средств! Нужно {format_number(price)}{MONEY}, у вас {format_number(bank)}{MONEY}", ephemeral=True)
            return
        
        # Списываем деньги
        add_bank(interaction.user.id, interaction.guild.id, -price)
        
        # Анимация открытия кейса
        animation_embed = create_embed(
            title="📦 Открытие кейса...",
            description="Кейс открывается...",
            color=discord.Color.from_str("#45248e"),
            author=interaction.user
        )
        await interaction.response.edit_message(embed=animation_embed, view=None)
        
        # Анимация (3 кадра)
        animation_frames = [
            "📦 Кейс открывается...",
            "✨ Светящиеся частицы...", 
            "🎁 Награда появляется..."
        ]
        
        message = await interaction.original_response()
        for frame in animation_frames:
            animation_embed.description = frame
            await message.edit(embed=animation_embed)
            await asyncio.sleep(0.8)
        
        # Выбираем награду
        if not rewards:
            await message.edit(embed=create_embed(title="❌ Ошибка", description="В кейсе нет наград", color=discord.Color.from_str("#45248e")), view=None)
            return
        
        weights = [int(r.get('chance', 1)) for r in rewards]
        reward = random.choices(rewards, weights=weights, k=1)[0]
        
        # Обрабатываем награду
        rtype = reward.get('type')
        embed = create_embed(
            title=f"📦 {name}",
            description=f"**Стоимость:** {format_number(price)}{MONEY}",
            color=discord.Color.from_str("#45248e"),
            author=interaction.user,
        )
        
        rarity = reward.get('rarity', 'Обычная')
        
        if rtype == 'money':
            amount = int(reward.get('amount', 0))
            add_bank(interaction.user.id, interaction.guild.id, amount)
            reward_name = reward.get('name', 'Деньги')
            embed.add_field(name="Награда", value=f"{reward_name}: {format_number(amount)}{MONEY}\n**Редкость:** {rarity}", inline=False)
        elif rtype == 'role':
            role_id = int(reward.get('role_id', 0))
            duration = int(reward.get('duration', 0))
            try:
                role = self.guild.get_role(role_id)
                if role:
                    member = self.guild.get_member(interaction.user.id)
                    if member:
                        await member.add_roles(role)
                        reward_name = reward.get('name', 'Роль')
                        if duration > 0:
                            embed.add_field(name="Награда", value=f"{reward_name}: {role.mention}\n⏱️ Временная ({duration//3600}ч)\n**Редкость:** {rarity}", inline=False)
                        else:
                            embed.add_field(name="Награда", value=f"{reward_name}: {role.mention}\n♾️ Постоянная\n**Редкость:** {rarity}", inline=False)
                    else:
                        embed.add_field(name="⚠️ Ошибка", value="Пользователь не найден на сервере", inline=False)
                else:
                    embed.add_field(name="⚠️ Ошибка", value="Роль не найдена на сервере", inline=False)
            except Exception as e:
                embed.add_field(name="⚠️ Ошибка", value=f"Не удалось выдать роль: {e}", inline=False)
        else:
            reward_name = reward.get('name', 'Неизвестная награда')
            embed.add_field(name="Награда", value=f"{reward_name}\n**Редкость:** {rarity}", inline=False)
        
        # Создаем новое view с кнопкой "Открыть еще один кейс"
        replay_view = CasesReplayView(self.guild, self.requester, self.cases_list, self.case_idx)
        await message.edit(embed=embed, view=replay_view)


class ShopView(ui.View):
    def __init__(self, guild: discord.Guild, requester: discord.Member, page: int = 0, order: str = 'price_desc', selected_item = None):
        super().__init__(timeout=None)
        self.guild = guild
        self.requester = requester
        self.page = page
        self.order = order
        self.selected_item = selected_item
        self._build_components()

    def _build_components(self):
        """Build UI components based on current state"""
        self.clear_items()
        
        if not self.selected_item:
            # Show sort select only when no item is selected
            filter_options = [
                discord.SelectOption(label="Цена: по убыванию", value="price_desc", emoji="📉"),
                discord.SelectOption(label="Цена: по возрастанию", value="price_asc", emoji="📈"),
                discord.SelectOption(label="Доступность", value="availability", emoji="📦"),
            ]
            filter_select = ui.Select(placeholder="Сортировка", options=filter_options, row=0)
            filter_select.callback = self.filter_select_callback
            self.add_item(filter_select)
            
        if not self.selected_item:
            # Show role selection and pagination
            items = get_market_items(self.guild.id, order=self.order, limit=5, offset=self.page*5)
            choose_options = []
            for i, it in enumerate(items):
                role = self.guild.get_role(it['role_id'])
                role_name = role.name if role else 'Неизвестно'
                description = it.get('description', 'Описание отсутствует')
                # Truncate description for select option
                if len(description) > 100:
                    description = description[:97] + "..."
                
                choose_options.append(discord.SelectOption(
                    label=role_name,
                    value=str(it['id'] if it['kind']=='shop' else it['role_id']),
                    description=description
                ))
            
            if not choose_options:
                choose_options = [discord.SelectOption(label="Пусто", value="none", description="Нет предметов")]
            
            choose_select = ui.Select(placeholder="Выберите роль для покупки", options=choose_options, row=1)
            choose_select.callback = self.choose_item_callback
            self.add_item(choose_select)
            
            # Pagination select
            total_items = len(get_market_items(self.guild.id, order=self.order, limit=1000, offset=0))
            total_pages = max(1, (total_items + 4) // 5)  # Round up
            
            if total_pages > 1:
                page_options = [
                    discord.SelectOption(label=f"Страница {i+1}", value=str(i))
                    for i in range(total_pages)
                ]
                page_select = ui.Select(placeholder=f"Страница {self.page + 1} из {total_pages}", options=page_options, row=2)
                page_select.callback = self.page_select_callback
                self.add_item(page_select)
        else:
            # Show only buy and cancel buttons
            cancel_btn = ui.Button(label="Отмена", style=discord.ButtonStyle.danger, row=1)
            cancel_btn.callback = self.cancel_callback
            self.add_item(cancel_btn)
            
            buy_btn = ui.Button(label="Купить", style=discord.ButtonStyle.success, row=1)
            buy_btn.callback = self.buy_callback
            self.add_item(buy_btn)

    def _update_buttons(self):
        """Update button states based on current state"""
        items = get_market_items(self.guild.id, order=self.order, limit=5, offset=self.page*5)
        total_items = len(get_market_items(self.guild.id, order=self.order, limit=1000, offset=0))
        
        for child in self.children:
            if isinstance(child, ui.Button):
                if child.label == "⬅️":
                    child.disabled = self.page == 0 or self.selected_item is not None
                elif child.label == "➡️":
                    child.disabled = (self.page + 1) * 5 >= total_items or self.selected_item is not None
                elif child.label == "Купить":
                    child.disabled = self.selected_item is None
                    child.style = discord.ButtonStyle.success if self.selected_item else discord.ButtonStyle.secondary
                elif child.label == "Отмена":
                    child.disabled = self.selected_item is None
                    child.style = discord.ButtonStyle.danger if self.selected_item else discord.ButtonStyle.secondary
            elif isinstance(child, ui.Select):
                child.disabled = self.selected_item is not None

    def build_embed(self) -> discord.Embed:
        if self.selected_item:
            # Show only selected item details
            role = self.guild.get_role(self.selected_item['role_id'])
            availability = "Без ограничений" if self.selected_item['stock'] is None else f"{self.selected_item['stock']} шт."
            description = self.selected_item.get('description', 'Описание отсутствует')
            
            if self.selected_item['kind'] == 'shop':
                src = "Магазин Naeratus"
                seller_avatar = self.guild.icon.url if self.guild.icon else None
            else:
                seller_id = self.selected_item['seller_user_id']
                seller = self.guild.get_member(seller_id)
                src = f"Продавец: {seller.display_name if seller else f'<@{seller_id}>'}"
                seller_avatar = seller.display_avatar.url if seller else None
            
            embed = create_embed(
                title=f"🛒 Покупка роли",
                description=f"**{role.name if role else 'Неизвестная роль'}**\n\n{description}",
                color=discord.Color.from_str("#45248e"),
                author=self.requester,
            )
            if role:
                embed.add_field(name="Роль", value=role.mention, inline=True)
                embed.add_field(name="Цена", value=f"**{format_number(self.selected_item['price'])}{MONEY}**", inline=True)
                embed.add_field(name="Доступно", value=availability, inline=True)
                embed.add_field(name="Источник", value=src, inline=False)
            
            # Set seller avatar as thumbnail
            if seller_avatar:
                embed.set_thumbnail(url=seller_avatar)
            else:
                embed.set_thumbnail(url=self.guild.icon.url if self.guild.icon else None)
            
            # Rebuild components for selected state
            self._build_components()
        else:
            # Show list of items
            items = get_market_items(self.guild.id, order=self.order, limit=5, offset=self.page*5)
            lines = []
            for idx, item in enumerate(items, start=1 + self.page*5):
                role = self.guild.get_role(item['role_id'])
                availability = "∞" if item['stock'] is None else str(item['stock'])
                role_text = role.mention if role else f"ID: {item['role_id']}"
                description = item.get('description', 'Описание отсутствует')
                # Truncate description if too long
                if len(description) > 50:
                    description = description[:47] + "..."
                lines.append(f"**#{idx}** {role_text}** — {format_number(item['price'])}{MONEY}**\n*{description}*\n📦 В наличии: {availability}\n")
                
            embed = create_embed(
                title="🛒 Магазин предметов Naeratus",
                description=("Выберите роль из списка ниже:\n\n" + "\n".join(lines)) if lines else "Магазин пуст",
                color=discord.Color.from_str("#45248e"),
                author=self.requester,
            )
            # Set server icon as thumbnail
            if self.guild.icon:
                embed.set_thumbnail(url=self.guild.icon.url)
            embed.set_footer(text=f"Страница {self.page + 1}")
            
            # Rebuild components for list state
            self._build_components()
        
        return embed

    async def filter_select_callback(self, interaction: discord.Interaction):
        self.order = interaction.data['values'][0]
        self.page = 0  # Reset to first page
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def choose_item_callback(self, interaction: discord.Interaction):
        val = interaction.data['values'][0]
        if val == "none":
            await interaction.response.defer()
            return
        
        items = get_market_items(self.guild.id, order=self.order, limit=5, offset=self.page*5)
        for it in items:
            if (it['kind']=='shop' and str(it['id'])==val) or (it['kind']!='shop' and str(it['role_id'])==val):
                self.selected_item = it
                break
        
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def page_select_callback(self, interaction: discord.Interaction):
        self.page = int(interaction.data['values'][0])
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def cancel_callback(self, interaction: discord.Interaction):
        self.selected_item = None
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def buy_callback(self, interaction: discord.Interaction):
        if not self.selected_item:
            await interaction.response.send_message("❌ Сначала выберите роль.", ephemeral=False)
            return
        
        kind = self.selected_item['kind']
        id_or_role = self.selected_item['id'] if kind=='shop' else self.selected_item['role_id']
        ok, msg, role_id, price = purchase_market_item(self.guild.id, interaction.user.id, kind, id_or_role)
        
        if ok:
            role = self.guild.get_role(role_id)
            if role:
                try:
                    await interaction.user.add_roles(role, reason="Покупка в магазине")
                    embed = create_embed(
                        title="✅ Покупка успешна!",
                        description=f"Вы купили роль {role.mention} за **{format_number(price)}{MONEY}**",
                        color=discord.Color.from_str("#45248e"),
                        author=interaction.user,
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=False)
                    # Reset and go back to list
                    self.selected_item = None
                    embed = self.build_embed()
                    await interaction.message.edit(embed=embed, view=self)
                    return
                except Exception as e:
                    msg = f"❌ Роль куплена, но не выдана: {e}"
        
        await interaction.response.send_message(msg, ephemeral=False)


def format_number(num: int) -> str:
    """Форматирует число с разделителями каждые 3 цифры"""
    return f"{num:,}".replace(",", ".")

class BalanceAmountModal(ui.Modal, title="Введите сумму"):
    amount = ui.TextInput(label="Сумма", required=True, placeholder="1000")
    balance_type = ui.TextInput(label="Тип баланса (cash/bank)", required=True, placeholder="bank", max_length=4)

    def __init__(self, action: str, guild: discord.Guild, target: discord.Member):
        super().__init__()
        self.action = action
        self.guild = guild
        self.target = target

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(str(self.amount.value).strip())
        except ValueError:
            await interaction.response.send_message("❌ Некорректная сумма", ephemeral=False)
            return

        balance_type = str(self.balance_type.value).strip().lower()
        if balance_type not in ['cash', 'bank']:
            await interaction.response.send_message("❌ Тип баланса должен быть 'cash' или 'bank'", ephemeral=False)
            return

        formatted_amount = format_number(amount)

        if self.action == 'add':
            if balance_type == 'bank':
                add_bank(self.target.id, self.guild.id, amount)
            else:
                add_cash(self.target.id, self.guild.id, amount)
            await interaction.response.send_message(f"✅ Добавлено {formatted_amount}{MONEY} на {balance_type} пользователя {self.target.mention}", ephemeral=False)
        elif self.action == 'remove':
            if balance_type == 'bank':
                add_bank(self.target.id, self.guild.id, -amount)
            else:
                add_cash(self.target.id, self.guild.id, -amount)
            await interaction.response.send_message(f"✅ Убрано {formatted_amount}{MONEY} с {balance_type} пользователя {self.target.mention}", ephemeral=False)
        elif self.action == 'set':
            from src.database.economy import set_money
            if balance_type == 'bank':
                set_money(self.target.id, self.guild.id, bank=amount)
            else:
                set_money(self.target.id, self.guild.id, cash=amount)
            await interaction.response.send_message(f"✅ Установлен {balance_type} баланс {formatted_amount}{MONEY} для пользователя {self.target.mention}", ephemeral=False)


class TempRoleModal(ui.Modal, title="Добавить временную роль"):
    role_id = ui.TextInput(label="ID роли", required=True, placeholder="123456789")
    duration = ui.TextInput(label="Длительность (секунды)", required=True, placeholder="3600")

    def __init__(self, guild: discord.Guild, target: discord.Member):
        super().__init__()
        self.guild = guild
        self.target = target

    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id = int(str(self.role_id.value).strip())
            duration = int(str(self.duration.value).strip())
        except ValueError:
            await interaction.response.send_message("❌ Некорректные данные", ephemeral=False)
            return

        role = self.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message("❌ Роль не найдена", ephemeral=False)
            return

        try:
            await self.target.add_roles(role, reason=f"Временная роль от {interaction.user}")
            until_ts = datetime.utcnow().timestamp() + duration
            set_temp_role(self.target.id, self.guild.id, role_id, until_ts)
            await interaction.response.send_message(
                f"✅ Роль {role.mention} выдана пользователю {self.target.mention} на {duration} секунд",
                ephemeral=False
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=False)


class AdminBalanceView(ui.View):
    def __init__(self, guild: discord.Guild, target: discord.Member):
        super().__init__(timeout=None)
        self.guild = guild
        self.target = target

    def build_embed(self) -> discord.Embed:
        acc = get_or_create_account(self.target.id, self.guild.id)
        cash, bank, xp, level, voice_seconds = acc[0], acc[1], acc[2], acc[3], acc[4]
        
        embed = create_embed(
            title=f"⚙️ Админ-панель: {self.target.display_name}",
            description=f"Управление балансом и ролями пользователя",
            color=discord.Color.from_str("#45248e"),
        )
        embed.set_thumbnail(url=self.target.display_avatar.url)
        embed.add_field(name="💵 Наличные", value=f"{cash}{MONEY}", inline=True)
        embed.add_field(name="🏦 Банк", value=f"{bank}{MONEY}", inline=True)
        embed.add_field(name="⭐ Уровень", value=f"{level} ({xp} XP)", inline=True)
        
        # Show custom roles
        roles_ids = get_owned_custom_roles(self.target.id, self.guild.id)
        if roles_ids:
            roles_list = [f"<@&{rid}>" for rid in roles_ids[:5]]
            embed.add_field(name="🎭 Кастомные роли", value="\n".join(roles_list) or "Нет", inline=False)
        
        return embed

    @ui.button(label="➕ Добавить баланс", style=discord.ButtonStyle.secondary, row=0)
    async def add_balance(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(BalanceAmountModal('add', self.guild, self.target))

    @ui.button(label="➖ Убрать баланс", style=discord.ButtonStyle.secondary, row=0)
    async def remove_balance(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(BalanceAmountModal('remove', self.guild, self.target))

    @ui.button(label="📝 Установить баланс", style=discord.ButtonStyle.secondary, row=0)
    async def set_balance(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(BalanceAmountModal('set', self.guild, self.target))

    @ui.button(label="⏱️ Добавить врем. роль", style=discord.ButtonStyle.secondary, row=1)
    async def add_temp_role(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(TempRoleModal(self.guild, self.target))

    @ui.button(label="🗑️ Удалить кастомные роли", style=discord.ButtonStyle.secondary, row=1)
    async def delete_custom_roles(self, interaction: discord.Interaction, button: ui.Button):
        roles_ids = get_owned_custom_roles(self.target.id, self.guild.id)
        if not roles_ids:
            await interaction.response.send_message("❌ У пользователя нет кастомных ролей", ephemeral=False)
            return
            
        view = DeleteRolesView(self.guild, self.target, roles_ids)
        await interaction.response.send_message("Выберите роли для удаления:", view=view, ephemeral=False)

    @ui.button(label="🔄 Обновить", style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction: discord.Interaction, button: ui.Button):
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)


class DeleteRolesView(ui.View):
    def __init__(self, guild: discord.Guild, target: discord.Member, roles_ids: list[int]):
        super().__init__(timeout=None)
        self.guild = guild
        self.target = target
        self.roles_ids = roles_ids
        
        # Create select with roles
        options = []
        for rid in roles_ids[:25]:  # Discord limit
            role = guild.get_role(rid)
            if role:
                options.append(discord.SelectOption(label=role.name, value=str(rid), description=f"ID: {rid}"))
        
        if options:
            select = ui.Select(placeholder="Выберите роли для удаления", options=options, min_values=1, max_values=len(options))
            select.callback = self.select_callback
            self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        selected_ids = [int(v) for v in interaction.data['values']]
        removed = []
        
        for rid in selected_ids:
            role = self.guild.get_role(rid)
            if role and role in self.target.roles:
                try:
                    await self.target.remove_roles(role, reason=f"Удалено админом {interaction.user}")
                    removed.append(role.mention)
                    # Remove from DB
                    from src.database.economy import get_connection
                    conn = get_connection()
                    c = conn.cursor()
                    c.execute("DELETE FROM owned_custom_roles WHERE user_id=? AND guild_id=? AND role_id=?",
                             (self.target.id, self.guild.id, rid))
                    conn.commit()
                    conn.close()
                except Exception:
                    pass
        
        if removed:
            await interaction.response.send_message(f"✅ Удалены роли: {', '.join(removed)}", ephemeral=False)
        else:
            await interaction.response.send_message("❌ Не удалось удалить роли", ephemeral=False)


def _parse_color(text: str) -> discord.Color:
    t = (text or '').strip().lower()
    named = {
        'red': discord.Color.red(),
        'green': discord.Color.green(),
        'blue': discord.Color.blue(),
        'purple': discord.Color.purple(),
        'orange': discord.Color.orange(),
        'teal': discord.Color.teal(),
        'grey': discord.Color.greyple(),
        'gray': discord.Color.greyple(),
        'gold': discord.Color.gold(),
    }
    if t in named:
        return named[t]
    if t.startswith('#'):
        t = t[1:]
    try:
        value = int(t, 16)
        return discord.Color(value)
    except Exception:
        return discord.Color.default()


class AdminShopRoleModal(ui.Modal, title="Добавить роль в магазин"):
    price = ui.TextInput(label="Цена", required=True, placeholder="1000")
    stock = ui.TextInput(label="Количество (пусто = без ограничений)", required=False, placeholder="10")
    description = ui.TextInput(label="Описание роли", required=True, placeholder="Краткое описание роли для покупателей", max_length=200)

    def __init__(self, guild: discord.Guild, role_id: int):
        super().__init__()
        self.guild = guild
        self.role_id = role_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price = int(self.price.value)
            if price <= 0:
                await interaction.response.send_message("❌ Цена должна быть положительным числом.", ephemeral=True)
                return
            
            stock = None
            if self.stock.value.strip():
                stock = int(self.stock.value)
                if stock <= 0:
                    await interaction.response.send_message("❌ Количество должно быть положительным числом.", ephemeral=True)
                    return
            
            description = str(self.description.value).strip()
            
            # Добавляем роль в магазин
            success, message = add_shop_role(
                self.guild.id, 
                self.role_id, 
                price, 
                stock, 
                description
            )
            
            if success:
                role = self.guild.get_role(self.role_id)
                role_name = role.name if role else f"ID: {self.role_id}"
                stock_text = f"Количество: {stock}" if stock else "Без ограничений"
                
                embed = create_embed(
                    title="✅ Роль добавлена в магазин",
                    description=f"**Роль:** {role_name}\n**Цена:** {format_number(price)}{MONEY}\n**{stock_text}**\n**Описание:** {description}",
                    color=discord.Color.green(),
                    author=interaction.user,
                )
                await interaction.response.send_message(embed=embed, ephemeral=False)
            else:
                await interaction.response.send_message(f"❌ {message}", ephemeral=True)
                
        except ValueError:
            await interaction.response.send_message("❌ Неверный формат числа.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)


class CustomRoleModal(ui.Modal, title="Создать кастомную роль"):
    name = ui.TextInput(label="Название роли", required=True, max_length=100)
    color = ui.TextInput(label="Цвет (название или #hex)", required=True, placeholder="#ff0000 или red")
    image_url = ui.TextInput(label="Изображение (URL, опционально)", required=False)

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        # Create request
        req_id = add_custom_role_request(interaction.user.id, interaction.guild.id, str(self.name.value).strip(), str(self.color.value).strip(), str(self.image_url.value or '').strip())
        # Post to review channel
        channel_id = getattr(settings, 'ECONOMY_REVIEW_CHANNEL_ID', None)
        if not channel_id:
            await interaction.response.send_message("❌ Канал ревью не настроен.", ephemeral=False)
            return
        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("❌ Канал ревью не найден.", ephemeral=False)
            return
        embed = create_embed(
            title="Заявка на кастомную роль",
            description=(
                f"Пользователь: {interaction.user.mention} (`{interaction.user.id}`)\n"
                f"Название: `{self.name.value}`\nЦвет: `{self.color.value}`\n"
                f"Картинка: {self.image_url.value or '—'}\nСтатус: На рассмотрении"
            ),
            color=discord.Color.from_str("#45248e"),
            author=interaction.user,
        )
        view = CustomRoleReviewView(self.bot, req_id)
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Заявка отправлена на рассмотрение.", ephemeral=False)


class CustomRoleStartView(ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @ui.button(label="Создать", style=discord.ButtonStyle.success)
    async def start(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(CustomRoleModal(self.bot))


class CustomRoleReviewView(ui.View):
    def __init__(self, bot: commands.Bot, req_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.req_id = req_id

    def _is_reviewer(self, member: discord.Member) -> bool:
        if member.guild_permissions.administrator:
            return True
        allowed = getattr(settings, 'ECONOMY_REVIEW_ROLES', [])
        return any(role.id in allowed for role in member.roles)

    @ui.button(label="Одобрить", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: ui.Button):
        if not self._is_reviewer(interaction.user):
            await interaction.response.send_message("❌ Нет доступа.", ephemeral=False)
            return
        row = get_request(self.req_id)
        if not row:
            await interaction.response.send_message("❌ Заявка не найдена.", ephemeral=False)
            return
        _, user_id, guild_id, name, color_text, image_url, status = row
        guild = interaction.guild
        # check funds now
        from src.database.economy import get_or_create_account, add_bank
        acc = get_or_create_account(user_id, guild_id)
        bank = acc[1] or 0
        price = getattr(settings, 'ECONOMY_CUSTOM_ROLE_PRICE', 5000)
        if bank < price:
            await interaction.response.send_message("❌ Недостаточно средств у пользователя.", ephemeral=False)
            set_request_status(self.req_id, 'denied', interaction.user.id)
            try:
                user = guild.get_member(user_id) or await guild.fetch_member(user_id)
                await user.send("❌ Ваша заявка отклонена: недостаточно средств на момент проверки.")
            except Exception:
                pass
            return
        # unique name
        if discord.utils.get(guild.roles, name=name):
            await interaction.response.send_message("❌ Роль с таким названием уже существует.", ephemeral=False)
            set_request_status(self.req_id, 'denied', interaction.user.id)
            try:
                user = guild.get_member(user_id) or await guild.fetch_member(user_id)
                await user.send("❌ Ваша заявка отклонена: роль с таким названием уже существует.")
            except Exception:
                pass
            return
        # create role
        try:
            role = await guild.create_role(name=name, colour=_parse_color(color_text), reason="Кастомная роль")
        except Exception as e:
            await interaction.response.send_message(f"❌ Не удалось создать роль: {e}", ephemeral=False)
            return
        # deduct funds and grant role
        add_bank(user_id, guild_id, -price)
        try:
            user = guild.get_member(user_id) or await guild.fetch_member(user_id)
            await user.add_roles(role, reason="Кастомная роль одобрена")
            add_owned_custom_role(user_id, guild_id, role.id)
            set_request_status(self.req_id, 'approved', interaction.user.id)
            
            # Update embed with approved status
            embed = create_embed(
                title="✅ Заявка на кастомную роль - ОДОБРЕНА",
                description=(
                    f"Пользователь: {user.mention} (`{user.id}`)\n"
                    f"Название: `{name}`\nЦвет: `{color_text}`\n"
                    f"Картинка: {image_url or '—'}\n"
                    f"Статус: **Одобрено**\n"
                    f"Модератор: {interaction.user.mention}"
                ),
                color=discord.Color.from_str("#45248e"),
                author=user,
            )
            embed.add_field(name="ID роли", value=f"`{role.id}`", inline=True)
            embed.add_field(name="Цена", value=f"{price}{MONEY}", inline=True)
            
            # Disable buttons
            for item in self.children:
                item.disabled = True
            
            await interaction.response.edit_message(embed=embed, view=self)
            
            # Send DM notification to user
            try:
                dm_embed = create_embed(
                    title="🎉 Кастомная роль одобрена!",
                    description=(
                        f"Ваша заявка на кастомную роль была **одобрена**!\n\n"
                        f"**Информация о роли:**\n"
                        f"• Название: `{name}`\n"
                        f"• ID: `{role.id}`\n"
                        f"• Цвет: `{color_text}`\n"
                        f"• Модератор: {interaction.user.display_name}"
                    ),
                    color=discord.Color.from_str("#45248e"),
                    author=user,
                )
                await user.send(embed=dm_embed)
            except Exception:
                pass
                
        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка при выдаче роли: {e}", ephemeral=False)

    @ui.button(label="Отклонить", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: ui.Button):
        if not self._is_reviewer(interaction.user):
            await interaction.response.send_message("❌ Нет доступа.", ephemeral=False)
            return
        
        row = get_request(self.req_id)
        if not row:
            await interaction.response.send_message("❌ Заявка не найдена.", ephemeral=False)
            return
        
        _, user_id, guild_id, name, color_text, image_url, status = row
        set_request_status(self.req_id, 'denied', interaction.user.id)
        
        # Update embed with denied status
        user = interaction.guild.get_member(user_id) or await interaction.guild.fetch_member(user_id)
        embed = create_embed(
            title="❌ Заявка на кастомную роль - ОТКЛОНЕНА",
            description=(
                f"Пользователь: {user.mention} (`{user.id}`)\n"
                f"Название: `{name}`\nЦвет: `{color_text}`\n"
                f"Картинка: {image_url or '—'}\n"
                f"Статус: **Отклонено**\n"
                f"Модератор: {interaction.user.mention}"
            ),
            color=discord.Color.from_str("#45248e"),
            author=user,
        )
        
        # Disable buttons
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Send DM notification to user
        try:
            dm_embed = create_embed(
                title="❌ Кастомная роль отклонена",
                description=(
                    f"К сожалению, ваша заявка на кастомную роль была **отклонена**.\n\n"
                    f"**Информация о заявке:**\n"
                    f"• Название: `{name}`\n"
                    f"• Цвет: `{color_text}`\n"
                    f"• Модератор: {interaction.user.display_name}"
                ),
                color=discord.Color.from_str("#45248e"),
                author=user,
            )
            await user.send(embed=dm_embed)
        except Exception:
            pass


class CoinflipView(ui.View):
    def __init__(self, user: discord.Member, guild_id: int, bet: int):
        super().__init__(timeout=30)
        self.user = user
        self.guild_id = guild_id
        self.bet = bet
        self.choice = None

    @ui.button(label="🦅 Орёл", style=discord.ButtonStyle.secondary)
    async def choose_eagle(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ Это не ваша игра!", ephemeral=False)
            return
        
        self.choice = "eagle"
        await self._flip_coin(interaction)

    @ui.button(label="🪙 Решка", style=discord.ButtonStyle.secondary)
    async def choose_tails(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ Это не ваша игра!", ephemeral=False)
            return
        
        self.choice = "tails"
        await self._flip_coin(interaction)

    async def _flip_coin(self, interaction: discord.Interaction):
        # Disable buttons
        for item in self.children:
            item.disabled = True
        
        # Start animation
        embed = discord.Embed(
            title="🪙 Подбрасывание монетки...",
            description="Монетка кружится в воздухе...",
            color=discord.Color.from_str("#45248e")
        )
        embed.set_thumbnail(url=self.user.display_avatar.url)
        
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Short animation (3 frames)
        animation_frames = [
            "🪙 Монетка подброшена...",
            "🔄 Монетка кружится...",
            "💫 Монетка падает..."
        ]
        
        message = await interaction.original_response()
        
        # Show animation
        for frame in animation_frames:
            embed.description = frame
            await message.edit(embed=embed)
            await asyncio.sleep(0.6)
        
        # Final result
        result = random.choice(["eagle", "tails"])
        win = result == self.choice
        
        result_emoji = "🦅" if result == "eagle" else "🪙"
        result_text = "**Орёл**" if result == "eagle" else "**Решка**"
        choice_text = "**Орёл**" if self.choice == "eagle" else "**Решка**"
        
        if win:
            add_bank(self.user.id, self.guild_id, self.bet)
            embed = discord.Embed(
                title="🎉 Победа!",
                description=f"Результат: {result_emoji} {result_text}\nВаш выбор: {choice_text}\n\n✅ **Вы выиграли {self.bet}{MONEY}!**",
                color=discord.Color.from_str("#45248e")
            )
        else:
            add_bank(self.user.id, self.guild_id, -self.bet)
            embed = discord.Embed(
                title="💔 Проигрыш",
                description=f"Результат: {result_emoji} {result_text}\nВаш выбор: {choice_text}\n\n❌ **Вы проиграли {self.bet}{MONEY}**",
                color=discord.Color.from_str("#45248e")
            )
        
        embed.set_thumbnail(url=self.user.display_avatar.url)
        
        # Создаем новое view с кнопкой "Сыграть еще раз"
        replay_view = CoinflipReplayView(self.user, self.guild_id, self.bet)
        await message.edit(embed=embed, view=replay_view)


class CoinflipReplayView(ui.View):
    def __init__(self, user: discord.Member, guild_id: int, bet: int):
        super().__init__(timeout=60)
        self.user = user
        self.guild_id = guild_id
        self.bet = bet

    @ui.button(label="🎮 Сыграть еще раз", style=discord.ButtonStyle.primary)
    async def play_again(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ Это не ваша игра!", ephemeral=True)
            return
        
        # Проверяем баланс
        acc = get_or_create_account(interaction.user.id, self.guild_id)
        bank = acc[1] or 0
        
        if bank < self.bet:
            await interaction.response.send_message(f"❌ Недостаточно средств! Нужно {self.bet}{MONEY}, у вас {bank}{MONEY}", ephemeral=True)
            return
        
        # Создаем новую игру
        view = CoinflipView(self.user, self.guild_id, self.bet)
        embed = discord.Embed(
            title="🪙 Орёл или решка?",
            description=f"Ставка: **{self.bet}{MONEY}**\nВыберите сторону монетки:",
            color=discord.Color.from_str("#45248e")
        )
        embed.set_thumbnail(url=self.user.display_avatar.url)
        
        await interaction.response.edit_message(embed=embed, view=view)


class TopView(ui.View):
    def __init__(self, guild: discord.Guild, requester: discord.Member):
        super().__init__(timeout=None)
        self.guild = guild
        self.requester = requester

    async def build_embed(self, metric: str) -> discord.Embed:
        if metric == "balance":
            rows = get_top_by_balance(self.guild.id)
            title = "Топ по балансу"
            lines = []
            current_idx = 1
            for row in rows:
                user_id, total, cash, bank = row
                try:
                    member = self.guild.get_member(user_id) or await self.guild.fetch_member(user_id)
                    lines.append(f"`{current_idx}` | {member.display_name}\nНаличка: {format_number(cash)}{MONEY} | В банке: {format_number(bank)}{MONEY}\nБаланс: {format_number(total)}{MONEY}")
                    current_idx += 1
                except:
                    # Пропускаем пользователей, которых нет на сервере
                    continue
        elif metric == "level":
            rows = ExperienceService.get_top_by_level(self.guild.id)
            title = "Топ по уровню"
            lines = []
            current_idx = 1
            for row in rows:
                user_id, level, xp = row
                try:
                    member = self.guild.get_member(user_id) or await self.guild.fetch_member(user_id)
                    # Get level info using service
                    level_info = ExperienceService.get_user_level_info(user_id, self.guild.id)
                    lines.append(f"`{current_idx}` | {member.display_name}\nУровень: **{level}** `[{xp}/{level_info['xp_to_next']}]`")
                    current_idx += 1
                except:
                    # Пропускаем пользователей, которых нет на сервере
                    continue
        elif metric == "messages":
            rows = MessageCounterService.get_top_by_messages(self.guild.id)
            title = "Топ по отправленным сообщениям"
            lines = []
            current_idx = 1
            for row in rows:
                user_id, messages = row
                try:
                    member = self.guild.get_member(user_id) or await self.guild.fetch_member(user_id)
                    lines.append(f"`{current_idx}` | {member.display_name}\nОтправленных сообщений: **{format_number(messages)}**")
                    current_idx += 1
                except:
                    # Пропускаем пользователей, которых нет на сервере
                    continue
        elif metric == "voice":
            rows = get_top_by_voice(self.guild.id)
            title = "Топ по войсу"
            lines = []
            current_idx = 1
            for row in rows:
                user_id, voice_seconds = row
                hours = int(voice_seconds // 3600)
                minutes = int((voice_seconds % 3600) // 60)
                seconds = int(voice_seconds % 60)
                try:
                    member = self.guild.get_member(user_id) or await self.guild.fetch_member(user_id)
                    lines.append(f"`{current_idx}` | {member.display_name}\nВремя в войсе: **{hours:02d}:{minutes:02d}:{seconds:02d}**")
                    current_idx += 1
                except:
                    # Пропускаем пользователей, которых нет на сервере
                    continue
        elif metric == "robberies":
            rows = get_top_by_robberies(self.guild.id)
            title = "Топ по ограблениям"
            lines = []
            current_idx = 1
            for row in rows:
                user_id, success, fail = row
                try:
                    member = self.guild.get_member(user_id) or await self.guild.fetch_member(user_id)
                    lines.append(f"`{current_idx}` | {member.display_name}\nУспешных ограблений: **{format_number(success)}**")
                    current_idx += 1
                except:
                    # Пропускаем пользователей, которых нет на сервере
                    continue
        elif metric == "clans":
            rows = get_top_clans_by_members(10)
            title = "Топ кланов по участникам"
            lines = []
            current_idx = 1
            for clan_id, clan_name, member_count in rows:
                lines.append(f"`{current_idx}` | **{clan_name}**\nУчастников: **{member_count}**")
                current_idx += 1

        # Get user's rank
        user_rank = self._get_user_rank(metric)
        
        if metric == "clans":
            embed = discord.Embed(
                title=title,
                description="🏰 Топ кланов по количеству участников",
                color=discord.Color.from_str("#45248e")
            )
        else:
            embed = discord.Embed(
                title=title,
                description=f"**{self.requester.display_name}**, ваша позиция в этом топе: `{user_rank}`",
                color=discord.Color.from_str("#45248e")
            )
        
        if lines:
            field_name = "🏆 Топ кланов" if metric == "clans" else "🏆 Топ участников"
            embed.add_field(
                name=field_name,
                value="\n\n".join(lines),
                inline=False
            )
        else:
            embed.add_field(
                name="📊 Данные",
                value="Нет данных для отображения",
                inline=False
            )
        
        embed.set_thumbnail(url=self.guild.icon.url if self.guild.icon else None)
        return embed

    def _get_user_rank(self, metric: str) -> int:
        if metric == "balance":
            return get_rank_by_balance(self.requester.id, self.guild.id)
        elif metric == "level":
            return ExperienceService.get_rank_by_level(self.requester.id, self.guild.id)
        elif metric == "messages":
            return MessageCounterService.get_rank_by_messages(self.requester.id, self.guild.id)
        elif metric == "voice":
            return get_rank_by_voice(self.requester.id, self.guild.id)
        elif metric == "robberies":
            return get_rank_by_robberies(self.requester.id, self.guild.id)
        elif metric == "clans":
            # Для кланов возвращаем 0, так как это не индивидуальный рейтинг
            return 0
        return 0

    @ui.select(placeholder="Выберите метрику топа", options=[
        discord.SelectOption(label="Топ по балансу", value="balance", emoji="💰"),
        discord.SelectOption(label="Топ по уровню", value="level", emoji="⭐"),
        discord.SelectOption(label="Топ по войсу", value="voice", emoji="🎤"),
        discord.SelectOption(label="Топ по сообщениям", value="messages", emoji="💬"),
        discord.SelectOption(label="Топ по ограблениям", value="robberies", emoji="🔫"),
        discord.SelectOption(label="Топ кланов", value="clans", emoji="🏰"),
    ])
    async def metric_select(self, interaction: discord.Interaction, select: ui.Select):
        metric = select.values[0]
        embed = await self.build_embed(metric)
        await interaction.response.edit_message(embed=embed, view=self)


# Mapping custom emojis for blackjack cards
CARD_EMOJIS = {
    # Spades
    "2♠": "<:2_spades:1430949444186144850>",
    "3♠": "<:3_spades:1430949422736347197>",
    "4♠": "<:4_spades:1430949431464825023>",
    "5♠": "<:5_spades:1430949556761264168>",
    "6♠": "<:6_spades:1430949415681527848>",
    "7♠": "<:7_spades:1430949579079286987>",
    "8♠": "<:8_spades:1430949536142200852>",
    "9♠": "<:9_spades:1430949549895323750>",
    "10♠": "<:10_spades:1430949510997213326>",
    "J♠": "<:jack_spades:1430949506270105691>",
    "Q♠": "<:queen_spades:1430949461697499176>",
    "K♠": "<:king_spades:1430949484128505924>",
    "A♠": "<:age_spades:1430949519931211858>",
    
    # Hearts
    # "2♥": "<:2_hearts:1430949508514320405>",  # Not available in new emoji set
    "3♥": "<:3_hearts:1430949433474023625>",
    "4♥": "<:4_hearts:1430949428818346226>",
    "5♥": "<:5_hearts:1430949553955143862>",
    "6♥": "<:6_hearts:1430949574368956467>",
    "7♥": "<:7_hearts:1430948998674387025>",
    "8♥": "<:8_hearts:1430949534216884376>",
    "9♥": "<:9_hearts:1430949548188106762>",
    "10♥": "<:10_hearts:1430949508514320405>",
    "J♥": "<:jack_hearts:1430949503690866838>",
    "Q♥": "<:queen__hearts:1430949489920708668>",
    "K♥": "<:king_hearts:1430949478659264542>",
    "A♥": "<:age_hearts:1430949517477412894>",
    
    # Diamonds
    "2♦": "<:2_diamonds:1430949457532420097>",
    "3♦": "<:3_diamonds:1430949435294224536>",
    "4♦": "<:4_diamonds:1430949426834182287>",
    "5♦": "<:5_diamonds:1430949442416021615>",
    "6♦": "<:6_diamonds:1430949564621525093>",
    "7♦": "<:7_diamonds:1430949417623748749>",
    "8♦": "<:8_diamonds:1430949532278980739>",
    "9♦": "<:9_diamonds:1430949546271314092>",
    "10♦": "<:10_diamonds:1430949525668761600>",
    "J♦": "<:jack_diamonds:1430949523856822446>",
    "Q♦": "<:queen_diamonds:1430949500519976982>",
    "K♦": "<:king_diamonds:1430949470069198868>",
    "A♦": "<:age_diamonds:1430949514956640347>",
    
    # Clubs
    "2♣": "<:2_clubs:1430949451350020319>",
    "3♣": "<:3_clubs:1430949440470122658>",
    "4♣": "<:4_clubs:1430949424758259833>",
    "5♣": "<:5_clubs:1430949437756280953>",
    "6♣": "<:6_clubs:1430949560540467393>",
    "7♣": "<:7_clubs:1430949420043731025>",
    "8♣": "<:8_clubs:1430949530089689149>",
    "9♣": "<:9_clubs:1430949538289549353>",
    # "10♣": "<:10_clubs:1430949525668761600>",  # Not available in new emoji set
    "J♣": "<:jack_clubs:1430949522032300123>",
    "Q♣": "<:queen_clubs:1430949496153706607>",
    "K♣": "<:king_clubs:1430949467225460888>",
    "A♣": "<:age_clubs:1430949513169866824>",
}

def _bj_card_value(card: str) -> int:
    rank = card[:-1]
    if rank in ["J", "Q", "K"]:
        return 10
    if rank == "A":
        return 11
    return int(rank)


def _bj_hand_value(cards: list[str]) -> int:
    total = sum(_bj_card_value(c) for c in cards)
    # adjust aces
    aces = sum(1 for c in cards if c.startswith("A"))
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


class BlackjackView(ui.View):
    def __init__(self, user: discord.Member, guild_id: int, bet: int, cog):
        super().__init__(timeout=60)  # 60 seconds timeout
        self.user = user
        self.guild_id = guild_id
        self.bet = bet
        self.cog = cog
        self.message = None  # Will be set after sending
        
        # Use only cards that have custom emojis
        self.deck = list(CARD_EMOJIS.keys())
        random.shuffle(self.deck)
        
        self.player = [self._draw(), self._draw()]
        self.dealer = [self._draw(), self._draw()]
        self.finished = False
        self.dealer_turn = False

    def _draw(self) -> str:
        return self.deck.pop()

    def _format_card(self, card: str) -> str:
        """Format card with custom emoji"""
        return CARD_EMOJIS.get(card, f"`{card}`")

    def build_embed(self, show_dealer_hand: bool = False) -> discord.Embed:
        pv = _bj_hand_value(self.player)
        
        if show_dealer_hand:
            dv = _bj_hand_value(self.dealer)
            dealer_cards = " ".join([self._format_card(c) for c in self.dealer])
        else:
            dv = _bj_hand_value([self.dealer[0]])
            dealer_cards = self._format_card(self.dealer[0])
        
        player_cards = " ".join([self._format_card(c) for c in self.player])
        
        turn_text = "**Ход дилера...**" if self.dealer_turn else f"**{self.user.display_name}**, ваш ход."
        
        embed = discord.Embed(
            title="Блек джек",
            description=f"{turn_text}\n\nСтавка: **{self.bet}{MONEY}**",
            color=discord.Color.from_str("#45248e")
        )
        embed.set_thumbnail(url=self.user.display_avatar.url)
        
        embed.add_field(
            name=f"Карты игрока ({pv})",
            value=player_cards if player_cards else "Нет карт",
            inline=True
        )
        embed.add_field(
            name=f"Карты дилера ({dv})",
            value=dealer_cards if dealer_cards else "Нет карт",
            inline=True
        )
        
        return embed

    async def _finish(self, interaction: discord.Interaction, result: str):
        """Finish the game and determine outcome"""
        self.finished = True
        self.dealer_turn = True
        
        # Disable buttons during dealer turn
        for child in self.children:
            if isinstance(child, ui.Button):
                child.disabled = True
        
        pv = _bj_hand_value(self.player)
        
        # Show dealer turn message
        await interaction.response.edit_message(embed=self.build_embed(show_dealer_hand=False), view=self)
        
        # Dealer plays with delay
        await asyncio.sleep(1.5)
        
        while _bj_hand_value(self.dealer) < 17:
            self.dealer.append(self._draw())
            await asyncio.sleep(0.5)  # Small delay for each card
        
        dv = _bj_hand_value(self.dealer)
        outcome = result
        
        if result == 'play':
            if pv > 21:
                outcome = 'lose'
            elif dv > 21 or pv > dv:
                outcome = 'win'
            elif pv < dv:
                outcome = 'lose'
            else:
                outcome = 'push'
        
        # Settle bet
        if outcome == 'blackjack':
            add_bank(self.user.id, self.guild_id, int(self.bet * 1.5))
            result_emoji = "🎉"
            result_title = "Блекджек!"
            result_text = f"Натуральный блекджек! Выигрыш: **+{int(self.bet*1.5)}{MONEY}**"
            color = discord.Color.from_str("#45248e")
        elif outcome == 'win':
            add_bank(self.user.id, self.guild_id, self.bet)
            result_emoji = "✅"
            result_title = "Победа!"
            result_text = f"Вы выиграли: **+{self.bet}{MONEY}**"
            color = discord.Color.from_str("#45248e")
        elif outcome == 'push':
            result_emoji = "🤝"
            result_title = "Ничья"
            result_text = "Ставка возвращена"
            color = discord.Color.from_str("#45248e")
        else:
            add_bank(self.user.id, self.guild_id, -self.bet)
            result_emoji = "❌"
            result_title = "Поражение"
            result_text = f"Вы проиграли: **-{self.bet}{MONEY}**"
            color = discord.Color.from_str("#45248e")
        
        player_cards = " ".join([self._format_card(c) for c in self.player])
        dealer_cards = " ".join([self._format_card(c) for c in self.dealer])
        
        embed = discord.Embed(
            title=f"{result_emoji} {result_title}",
            description=result_text,
            color=discord.Color.from_str("#45248e")
        )
        embed.set_thumbnail(url=self.user.display_avatar.url)
        embed.add_field(
            name=f"Карты игрока ({pv})",
            value=player_cards,
            inline=True
        )
        embed.add_field(
            name=f"Карты дилера ({dv})",
            value=dealer_cards,
            inline=True
        )
        
        # Remove from active games
        if hasattr(self.cog, '_active_blackjack_games'):
            self.cog._active_blackjack_games.discard(self.user.id)
        
        # Создаем новое view с кнопкой "Сыграть еще раз"
        replay_view = BlackjackReplayView(self.user, self.guild_id, self.bet, self.cog)
        
        # Use stored message reference instead of interaction.message
        if self.message:
            await self.message.edit(embed=embed, view=replay_view)

    async def on_timeout(self):
        """Handle timeout - player loses"""
        if not self.finished:
            self.finished = True
            add_bank(self.user.id, self.guild_id, -self.bet)
            
            embed = discord.Embed(
                title="⏰ Время вышло",
                description=f"Вы не ответили в течение минуты и автоматически проиграли.\n\nПотеря: **-{self.bet}{MONEY}**",
                color=discord.Color.from_str("#45248e")
            )
            embed.set_thumbnail(url=self.user.display_avatar.url)
            
            # Remove from active games
            if hasattr(self.cog, '_active_blackjack_games'):
                self.cog._active_blackjack_games.discard(self.user.id)
            
        for child in self.children:
            if isinstance(child, ui.Button):
                child.disabled = True
            
            # Try to edit message
            try:
                await self.message.edit(embed=embed, view=self)
            except:
                pass

    @ui.button(label="Взять карту", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Это не ваша игра.", ephemeral=False)
            return
        if self.finished or self.dealer_turn:
            await interaction.response.defer()
            return
        
        self.player.append(self._draw())
        pv = _bj_hand_value(self.player)
        
        # Обновляем сообщение с картами игрока
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        
        # Если игрок перебрал или набрал 21, сразу завершаем игру
        if pv > 21:
            # Игрок перебрал - сразу завершаем без хода дилера
            await self._finish_dealer_turn(interaction, 'lose')
        elif pv == 21:
            # Игрок набрал 21 - сразу переходим к дилеру без задержки
            await self._dealer_turn(interaction)
        else:
            # Продолжаем игру - игрок может взять еще карту
            pass

    @ui.button(label="Остановиться", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Это не ваша игра.", ephemeral=False)
            return
        if self.finished or self.dealer_turn:
            await interaction.response.defer()
            return
        
        # Игрок остановился, переходим к дилеру
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        # Переходим к дилеру сразу без задержки
        await self._dealer_turn(interaction)

    async def _dealer_turn(self, interaction: discord.Interaction):
        """Ход дилера с анимацией"""
        self.dealer_turn = True
        
        # Отключаем кнопки
        for child in self.children:
            if isinstance(child, ui.Button):
                child.disabled = True
        
        # Показываем сообщение о ходе дилера
        embed = self.build_embed(show_dealer_hand=True)
        embed.title = "🎯 Ход дилера..."
        embed.description = "Дилер раздает себе карты..."
        
        await interaction.edit_original_response(embed=embed, view=self)
        
        # Дилер берет карты по правилам (до 17)
        while _bj_hand_value(self.dealer) < 17:
            await asyncio.sleep(1.0)  # Пауза между картами
            self.dealer.append(self._draw())
            
            # Обновляем отображение
            embed = self.build_embed(show_dealer_hand=True)
            embed.title = "🎯 Ход дилера..."
            embed.description = f"Дилер взял карту... (Сумма: {_bj_hand_value(self.dealer)})"
            
            await interaction.edit_original_response(embed=embed, view=self)
        
        # Завершаем игру - используем edit_original_response вместо response
        await self._finish_dealer_turn(interaction, 'play')

    async def _finish_dealer_turn(self, interaction: discord.Interaction, result: str):
        """Finish the game after dealer turn - uses edit_original_response"""
        self.finished = True
        
        pv = _bj_hand_value(self.player)
        dv = _bj_hand_value(self.dealer)
        outcome = result
        
        if result == 'play':
            if pv > 21:
                outcome = 'lose'
            elif dv > 21 or pv > dv:
                outcome = 'win'
            elif pv < dv:
                outcome = 'lose'
            else:
                outcome = 'push'
        
        # Settle bet
        if outcome == 'blackjack':
            add_bank(self.user.id, self.guild_id, int(self.bet * 1.5))
            result_emoji = "🎉"
            result_title = "Блекджек!"
            result_text = f"Натуральный блекджек! Выигрыш: **+{int(self.bet*1.5)}{MONEY}**"
            color = discord.Color.from_str("#45248e")
        elif outcome == 'win':
            add_bank(self.user.id, self.guild_id, self.bet)
            result_emoji = "✅"
            result_title = "Победа!"
            result_text = f"Вы выиграли: **+{self.bet}{MONEY}**"
            color = discord.Color.from_str("#45248e")
        elif outcome == 'push':
            result_emoji = "🤝"
            result_title = "Ничья"
            result_text = "Ставка возвращена"
            color = discord.Color.from_str("#45248e")
        else:
            add_bank(self.user.id, self.guild_id, -self.bet)
            result_emoji = "❌"
            result_title = "Поражение"
            result_text = f"Вы проиграли: **-{self.bet}{MONEY}**"
            color = discord.Color.from_str("#45248e")
        
        player_cards = " ".join([self._format_card(c) for c in self.player])
        dealer_cards = " ".join([self._format_card(c) for c in self.dealer])
        
        embed = discord.Embed(
            title=f"{result_emoji} {result_title}",
            description=result_text,
            color=discord.Color.from_str("#45248e")
        )
        embed.set_thumbnail(url=self.user.display_avatar.url)
        embed.add_field(
            name=f"Карты игрока ({pv})",
            value=player_cards,
            inline=True
        )
        embed.add_field(
            name=f"Карты дилера ({dv})",
            value=dealer_cards,
            inline=True
        )
        
        # Remove from active games
        if hasattr(self.cog, '_active_blackjack_games'):
            self.cog._active_blackjack_games.discard(self.user.id)
        
        # Создаем новое view с кнопкой "Сыграть еще раз"
        replay_view = BlackjackReplayView(self.user, self.guild_id, self.bet, self.cog)
        
        # Use edit_original_response instead of response.edit_message
        await interaction.edit_original_response(embed=embed, view=replay_view)


class BlackjackReplayView(ui.View):
    def __init__(self, user: discord.Member, guild_id: int, bet: int, cog):
        super().__init__(timeout=60)
        self.user = user
        self.guild_id = guild_id
        self.bet = bet
        self.cog = cog

    @ui.button(label="🎮 Сыграть еще раз", style=discord.ButtonStyle.primary)
    async def play_again(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ Это не ваша игра!", ephemeral=True)
            return
        
        # Проверяем баланс
        acc = get_or_create_account(interaction.user.id, self.guild_id)
        bank = acc[1] or 0
        
        if bank < self.bet:
            await interaction.response.send_message(f"❌ Недостаточно средств! Нужно {self.bet}{MONEY}, у вас {bank}{MONEY}", ephemeral=True)
            return
        
        # Создаем новую игру
        view = BlackjackView(self.user, self.guild_id, self.bet, self.cog)
        embed = view.build_embed()
        embed.title = "🃏 Блекджек"
        embed.description = f"Ставка: **{self.bet}{MONEY}**\nВыберите действие:"
        
        await interaction.response.edit_message(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))


