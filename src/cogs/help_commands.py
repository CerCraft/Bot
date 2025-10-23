import discord
from discord.ext import commands
from discord import app_commands, ui
from src.core.config import settings
from src.utils.embed import create_embed, EmbedColors


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Показать список команд бота")
    async def help_command(self, interaction: discord.Interaction):
        """Команда помощи с выпадающим списком для разных ролей"""
        view = HelpView(interaction.user)
        
        embed = create_embed(
            title="Справка по командам Naeratus Bot",
            description="Выберите категорию команд из выпадающего списка ниже:",
            color=EmbedColors.INFO,
            author=interaction.user
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.add_field(
            name="Информация",
            value="• Используйте выпадающий список для навигации\n• Некоторые команды доступны только определенным ролям\n• Все команды работают через слэш-команды",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)


class HelpView(ui.View):
    def __init__(self, user: discord.Member):
        super().__init__(timeout=300)
        self.user = user
        self.add_item(HelpSelect(user))


class HelpSelect(ui.Select):
    def __init__(self, user: discord.Member):
        self.user = user
        
        # Получаем роли пользователя
        user_roles = [role.id for role in user.roles]
        
        # Базовые опции для всех пользователей
        options = [
            discord.SelectOption(
                label="Общие команды",
                value="general",
                emoji="🏠"
            ),
            discord.SelectOption(
                label="Экономика",
                value="economy",
                emoji="💰"
            ),
            discord.SelectOption(
                label="Отношения",
                value="love",
                emoji="💕"
            ),
            discord.SelectOption(
                label="Кланы",
                value="clans",
                emoji="👥"
            ),
        ]
        
        # Проверяем права администратора
        has_admin_access = (
            any(role_id in settings.moderator_command_clear for role_id in user_roles) or
            user.guild_permissions.administrator
        )
        
        if has_admin_access:
            options.append(discord.SelectOption(
                label="Администраторы",
                value="admin",
                emoji="🛡️"
            ))
        
        # Проверяем права разработчика (если есть специальные роли)
        has_dev_access = (
            any(role_id in settings.ECONOMY_ADMIN_ROLES for role_id in user_roles) or
            user.guild_permissions.administrator
        )
        
        if has_dev_access:
            options.append(discord.SelectOption(
                label="Разработчик",
                value="developer",
                emoji="⚙️"
            ))
        
        super().__init__(placeholder="Выберите категорию команд...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ Только инициатор может использовать это меню.", ephemeral=True)
            return
            
        category = self.values[0]
        embed = self.build_help_embed(category, interaction.user)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    def build_help_embed(self, category: str, user: discord.Member) -> discord.Embed:
        """Создает эмбед с командами для выбранной категории"""
        
        if category == "general":
            return self._build_general_embed(user)
        elif category == "economy":
            return self._build_economy_embed(user)
        elif category == "love":
            return self._build_love_embed(user)
        elif category == "clans":
            return self._build_clans_embed(user)
        elif category == "tickets":
            return self._build_tickets_embed(user)
        elif category == "admin":
            return self._build_admin_embed(user)
        elif category == "developer":
            return self._build_developer_embed(user)
        else:
            return create_embed(
                title="❌ Ошибка",
                description="Неизвестная категория команд",
                color=EmbedColors.ERROR,
                author=user
            )

    def _build_general_embed(self, user: discord.Member) -> discord.Embed:
        embed = create_embed(
            title="🏠 Общие команды",
            description="Основные команды, доступные всем пользователям:",
            color=EmbedColors.INFO,
            author=user
        )
        
        embed.add_field(
            name="Профиль и статистика",
            value="• `/balance` - Показать баланс и профиль\n• `/top` - Топ игроков по различным критериям",
            inline=False
        )
        
        embed.add_field(
            name="Игры и развлечения",
            value="• `/coinflip` - Орел или решка\n• `/blackjack` - Игра в блекджек\n• `/cases` - Открыть кейсы",
            inline=False
        )
        
        embed.add_field(
            name="ℹИнформация",
            value="• `/help` - Показать это меню помощи",
            inline=False
        )
        
        return embed

    def _build_economy_embed(self, user: discord.Member) -> discord.Embed:
        embed = create_embed(
            title="💰 Экономика",
            description="Команды экономической системы:",
            color=EmbedColors.SUCCESS,
            author=user
        )
        
        embed.add_field(
            name="Основные команды",
            value="• `/balance` - Показать баланс и профиль\n• `/shop` - Магазин предметов\n• `/top` - Топ по балансу/уровню",
            inline=False
        )
        
        embed.add_field(
            name="Работа и заработок",
            value="• `/daily` - Ежедневная награда\n• `/work` - Работать за деньги\n• `/weekly` - Еженедельная награда",
            inline=False
        )
        
        embed.add_field(
            name="Азартные игры",
            value="• `/coinflip` - Орел или решка\n• `/blackjack` - Блекджек против дилера\n• `/rob` - Ограбить пользователя",
            inline=False
        )
        
        embed.add_field(
            name="Кейсы и награды",
            value="• `/cases` - Открыть кейсы с наградами",
            inline=False
        )
        
        embed.add_field(
            name="Кастомные роли",
            value="• `/buy_custom_role` - Создать кастомную роль",
            inline=False
        )
        
        return embed

    def _build_love_embed(self, user: discord.Member) -> discord.Embed:
        embed = create_embed(
            title="💕 Отношения",
            description="Команды для создания пар и отношений:",
            color=EmbedColors.INFO,
            author=user
        )
        
        embed.add_field(
            name="Основные команды",
            value="• `/love` - Показать профиль вашей пары\n• `/marry` - Предложить создать пару\n• `/divorce` - Расторгнуть пару",
            inline=False
        )
        
        embed.add_field(
            name="Свадьба",
            value="• Создайте пару с помощью `/marry`\n• Получите доступ к приватным комнатам\n• Показывайте свой статус отношений",
            inline=False
        )
        
        return embed

    def _build_clans_embed(self, user: discord.Member) -> discord.Embed:
        embed = create_embed(
            title="👥 Кланы",
            description="Команды для управления кланами:",
            color=EmbedColors.INFO,
            author=user
        )
        
        embed.add_field(
            name="Основные команды",
            value="• `/clan` - Управление кланом\n• `/clan_manage` - Панель управления (владельцы)\n• `/clan_id` - Узнать ID клана",
            inline=False
        )
        
        embed.add_field(
            name="Участники",
            value="• `/clan_invite` - Пригласить игрока в клан\n• Управление участниками клана\n• Система ролей в клане",
            inline=False
        )
        
        return embed

    def _build_tickets_embed(self, user: discord.Member) -> discord.Embed:
        embed = create_embed(
            title="🎫 Тикеты",
            description="Система поддержки и обращений:",
            color=EmbedColors.INFO,
            author=user
        )
        
        embed.add_field(
            name="Создание тикетов",
            value="• Используйте кнопки в специальных каналах\n• Выберите тип обращения\n• Опишите вашу проблему",
            inline=False
        )
        
        embed.add_field(
            name="Типы обращений",
            value="• **Жалоба на сервер** - Проблемы с сервером\n• **Жалоба на модерацию** - Апелляция наказаний\n• **Техподдержка** - Технические проблемы\n• **Подача на стафф** - Заявка на должность",
            inline=False
        )
        
        return embed

    def _build_admin_embed(self, user: discord.Member) -> discord.Embed:
        embed = create_embed(
            title="🛡️ Администраторы",
            description="Команды модерации и администрирования:",
            color=EmbedColors.WARNING,
            author=user
        )
        
        embed.add_field(
            name="Модерация",
            value="• `/clear` - Очистить сообщения в канале\n• `/moderate` - Панель модерации пользователя",
            inline=False
        )
        
        embed.add_field(
            name="Дисциплина",
            value="• `/warn` - Выдать предупреждение\n• `/warn_remove` - Снять предупреждение\n• `/strike` - Выдать страйк\n• `/praise` - Выдать похвалу\n• `/discipline_info` - Информация о дисциплине",
            inline=False
        )
        
        embed.add_field(
            name="Экономика (админ)",
            value="• `/admin_balance` - Админ-панель экономики\n• `/admin_role_shop` - Добавить роль в магазин\n• `/unarrest` - Снять арест с пользователя",
            inline=False
        )
        
        embed.add_field(
            name="Кланы (админ)",
            value="• `/clan_sync` - Синхронизация участников кланов\n• `/clan_setup` - Настройка каналов кланов",
            inline=False
        )
        
        return embed

    def _build_developer_embed(self, user: discord.Member) -> discord.Embed:
        embed = create_embed(
            title="⚙️ Разработчик",
            description="Технические команды для разработчиков:",
            color=EmbedColors.ERROR,
            author=user
        )
        
        embed.add_field(
            name="Сброс кулдаунов",
            value="• `/reset_cooldowns` - Сбросить все кулдауны\n• `/reset_daily` - Сбросить кулдаун daily\n• `/reset_work` - Сбросить кулдаун work\n• `/reset_weekly` - Сбросить кулдаун weekly\n• `/reset_rob` - Сбросить кулдаун rob",
            inline=False
        )
        
        embed.add_field(
            name="Проверка состояния",
            value="• `/check_cooldowns` - Проверить кулдауны пользователя\n• `/dev_info` - Информация о боте",
            inline=False
        )
        
        embed.add_field(
            name="Принудительное выполнение",
            value="• `/force_daily` - Принудительно выполнить daily\n• `/force_work` - Принудительно выполнить work\n• `/force_weekly` - Принудительно выполнить weekly",
            inline=False
        )
        
        embed.add_field(
            name="Настройка кланов",
            value="• `/clan_find_channel` - Поиск канала для кланов\n• `/clan_set_channel` - Установка канала по ID\n• `/clan_info` - Создать информационное сообщение",
            inline=False
        )
        
        return embed


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
