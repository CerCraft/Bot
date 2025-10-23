# src/cogs/clans.py
import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
from datetime import datetime, timedelta, timezone
import asyncio
import logging
from typing import Optional

from src.core.config import settings
from src.utils.embed import create_embed, EmbedColors
from src.database.clans import (
    init_clans_db,
    create_clan,
    get_clan_by_id,
    get_clan_by_name,
    get_user_clan,
    get_clan_members,
    add_clan_member,
    remove_clan_member,
    update_clan_info,
    update_clan_max_members,
    update_clan_member_role,
    get_clan_member_role,
    add_clan_voice_channel,
    get_clan_voice_channels,
    get_all_clans,
    update_clan_payment,
    deactivate_clan,
    get_clans_for_payment,
    get_connection
)
from src.database.economy import get_or_create_account, add_cash, transfer_cash_to_bank

# Словарь для преобразования Discord кодов эмодзи в Unicode
EMOJI_MAP = {
    ':zap:': '⚡',
    ':shield:': '🛡️',
    ':crossed_swords:': '⚔️',
    ':fire:': '🔥',
    ':star:': '⭐',
    ':crown:': '👑',
    ':gem:': '💎',
    ':rocket:': '🚀',
    ':skull:': '💀',
    ':heart:': '❤️',
    ':boom:': '💥',
    ':lightning:': '⚡',
    ':dagger:': '🗡️',
    ':dagger_knife:': '🗡️',
    ':bow_and_arrow:': '🏹',
    ':hammer:': '🔨',
    ':axe:': '🪓',
    ':trident:': '🔱',
    ':magic_wand:': '🪄',
    ':crystal_ball:': '🔮',
    ':dragon:': '🐉',
    ':wolf:': '🐺',
    ':lion:': '🦁',
    ':tiger:': '🐯',
    ':eagle:': '🦅',
    ':snake:': '🐍',
    ':bat:': '🦇',
    ':bear:': '🐻',
    ':fox:': '🦊',
    ':panda:': '🐼',
    ':koala:': '🐨',
    ':mountain:': '⛰️',
    ':snowflake:': '❄️',
    ':sunny:': '☀️',
    ':moon:': '🌙',
    ':cloud:': '☁️',
    ':tornado:': '🌪️',
    ':ocean:': '🌊',
    ':herb:': '🌿',
    ':shamrock:': '☘️',
    ':four_leaf_clover:': '🍀',
    ':rose:': '🌹',
    ':cherry_blossom:': '🌸',
    ':sunflower:': '🌻',
    ':dart:': '🎯',
    ':100:': '💯',
    ':muscle:': '💪',
    ':fist:': '✊',
    ':crossed_flags:': '🎌',
    ':jp:': '🇯🇵',
    ':us:': '🇺🇸',
    ':ru:': '🇷🇺',
    ':fr:': '🇫🇷',
    ':gb:': '🇬🇧',
    ':de:': '🇩🇪',
    ':pirate_flag:': '🏴‍☠️',
    ':rainbow_flag:': '🏳️‍🌈',
}

def convert_emoji(emoji_text: str) -> str:
    """Преобразует Discord коды эмодзи в Unicode эмодзи"""
    if not emoji_text:
        return '🛡️'
    
    # Если это уже Unicode эмодзи или кастомная Discord эмодзи (<:name:id>)
    if not emoji_text.startswith(':') or emoji_text.startswith('<:'):
        return emoji_text
    
    # Преобразуем Discord код в Unicode
    return EMOJI_MAP.get(emoji_text.lower(), emoji_text)

def check_user_in_clan(user: discord.Member, guild: discord.Guild) -> Optional[dict]:
    """
    Проверяет, состоит ли пользователь в клане.
    Сначала проверяет БД, затем проверяет наличие роли клана.
    Если есть роль, но нет в БД - добавляет в БД.
    """
    # Проверяем в базе данных
    user_clan = get_user_clan(user.id)
    if user_clan:
        return user_clan
    
    # Проверяем наличие роли клана
    all_clans = get_all_clans()
    for clan in all_clans:
        role = guild.get_role(clan['role_id'])
        if role and role in user.roles:
            # У пользователя есть роль клана, но нет записи в БД - добавляем
            logging.info(f"Пользователь {user.id} имеет роль клана {clan['name']}, но нет в БД. Добавляем...")
            add_clan_member(clan['id'], user.id, 'member')
            return clan
    
    return None

class CreateClanModal(ui.Modal, title="Создание клана"):
    def __init__(self):
        super().__init__()
        
    name = ui.TextInput(
        label="Название клана",
        placeholder="Введите название клана...",
        max_length=32,
        required=True
    )
    
    emoji = ui.TextInput(
        label="Эмодзи клана",
        placeholder="Например: 🛡️ или :zap: или :fire:",
        max_length=30,
        required=False,
        default="🛡️"
    )
    
    description = ui.TextInput(
        label="Описание клана",
        placeholder="Введите описание клана...",
        max_length=200,
        required=True,
        style=discord.TextStyle.paragraph
    )
    
    color = ui.TextInput(
        label="Цвет клана (hex код)",
        placeholder="Например: #FF0000",
        max_length=7,
        required=True
    )
    
    avatar = ui.TextInput(
        label="Аватар клана (URL изображения)",
        placeholder="Ссылка на изображение (необязательно)",
        max_length=200,
        required=False
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        # Откладываем ответ, чтобы предотвратить таймаут взаимодействия
        await interaction.response.defer(ephemeral=True)
        
        # Проверяем, что пользователь не состоит в клане
        user_clan = check_user_in_clan(interaction.user, interaction.guild)
        if user_clan:
            embed = create_embed(
                title="❌ Ошибка",
                description="Вы уже состоите в клане!",
                color=EmbedColors.ERROR
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Проверяем, что клан с таким именем не существует
        existing_clan = get_clan_by_name(self.name.value, include_inactive=True)
        if existing_clan:
            embed = create_embed(
                title="❌ Ошибка",
                description="Клан с таким названием уже существует!",
                color=EmbedColors.ERROR
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
    
        # Проверяем баланс пользователя
        account = get_or_create_account(interaction.user.id, interaction.guild.id)
        cash = account[0]  # Первый элемент кортежа - cash
        if cash < settings.CLAN_CREATE_COST:
            embed = create_embed(
                title="❌ Недостаточно средств",
                description=f"Для создания клана нужно {settings.CLAN_CREATE_COST} {settings.ECONOMY_SYMBOL}",
                color=EmbedColors.ERROR
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Проверяем валидность hex цвета
        try:
            color_hex = self.color.value.lstrip('#')
            color_int = int(color_hex, 16)
        except ValueError:
            embed = create_embed(
                title="❌ Ошибка",
                description="Неверный формат цвета! Используйте hex код (например: #FF0000)",
                color=EmbedColors.ERROR
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Проверяем уникальность имени клана
        existing_clan = get_clan_by_name(self.name.value, include_inactive=True)
        if existing_clan:
            embed = create_embed(
                title="❌ Имя занято",
                description=f"Клан с именем **{self.name.value}** уже существует! Выберите другое имя.",
                color=EmbedColors.ERROR
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Создаем клан
        try:
            # Получаем эмодзи (по умолчанию 🛡️) и преобразуем Discord коды
            clan_emoji = convert_emoji(self.emoji.value) if self.emoji.value else '🛡️'
            
            # Создаем роль
            role = await interaction.guild.create_role(
                name=f"{self.name.value} clxn",
                color=discord.Color(color_int),
                mentionable=True
            )
        
            # Создаем текстовый канал
            # Формат: эмодзи-название клана-clnx
            text_category = interaction.guild.get_channel(settings.CLAN_TEXT_CATEGORY_ID)
            if not text_category:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Категория для текстовых каналов кланов не настроена!",
                    color=EmbedColors.ERROR
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            text_channel = await text_category.create_text_channel(
                name=f"{clan_emoji}-{self.name.value.lower().replace(' ', '-')}-clnx",
                topic=f"Канал клана {self.name.value}"
            )
        
            # Создаем голосовой канал
            # Формат: эмодзи ・ название клана
            voice_category = interaction.guild.get_channel(settings.CLAN_VOICE_CATEGORY_ID)
            if not voice_category:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Категория для голосовых каналов кланов не настроена!",
                    color=EmbedColors.ERROR
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            voice_channel = await voice_category.create_voice_channel(
                name=f"{clan_emoji} ・ {self.name.value} 1",
                user_limit=20  # По умолчанию 20 слотов
            )
        
            # Настраиваем права доступа
            # Текстовый канал - только участники клана могут видеть и писать
            await text_channel.set_permissions(interaction.guild.default_role, view_channel=False)
            await text_channel.set_permissions(role, read_messages=True, send_messages=True)
            
            # Голосовой канал - все могут видеть, только участники клана могут подключаться
            await voice_channel.set_permissions(interaction.guild.default_role, view_channel=True, connect=False)
            await voice_channel.set_permissions(role, connect=True, speak=True)
        
            # Создаем запись в базе данных
            logging.info(f"Создаем клан с ID:")
            logging.info(f"- Роль: {role.id}")
            logging.info(f"- Текстовый канал: {text_channel.id}")
            logging.info(f"- Голосовой канал: {voice_channel.id}")
            
            clan_id = create_clan(
                name=self.name.value,
                description=self.description.value,
                color=color_int,
                owner_id=interaction.user.id,
                role_id=role.id,
                text_channel_id=text_channel.id,
                voice_channel_id=voice_channel.id,
                avatar_url=self.avatar.value if self.avatar.value else None,
                emoji=clan_emoji
            )
        
            # Дополнительная проверка: убеждаемся, что владелец добавлен как участник
            if not check_user_in_clan(interaction.user, interaction.guild):
                add_clan_member(clan_id, interaction.user.id, 'owner')
                logging.warning(f"Владелец клана {clan_id} не был найден в участниках, добавлен принудительно")
            
            # Списываем деньги
            add_cash(interaction.user.id, interaction.guild.id, -settings.CLAN_CREATE_COST)
            
            # Даем роль владельца клана
            owner_role = interaction.guild.get_role(settings.CLAN_OWNER_ROLE_ID)
            if owner_role:
                await interaction.user.add_roles(role, owner_role)
            else:
                await interaction.user.add_roles(role)
        
            embed = create_embed(
                title="🎉 Клан создан!",
                description=f"Клан **{self.name.value}** успешно создан!\n\n"
                           f"💰 Потрачено: {settings.CLAN_CREATE_COST} {settings.ECONOMY_SYMBOL}\n"
                           f"📝 Описание: {self.description.value}\n"
                           f"🎨 Цвет: {self.color.value}\n"
                           f"👑 Владелец: {interaction.user.mention}",
                color=EmbedColors.SUCCESS
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Отправляем приветственное сообщение в канал клана
            welcome_embed = create_embed(
                title=f"🏰 Добро пожаловать в клан {self.name.value}!",
                description=f"Это канал вашего клана.\n\n"
                           f"📝 Описание: {self.description.value}\n"
                           f"👑 Владелец: {interaction.user.mention}\n"
                           f"👥 Участников: 1/{settings.CLAN_DEFAULT_MAX_MEMBERS}",
                color=color_int
            )
            await text_channel.send(embed=welcome_embed)
        
        except Exception as e:
            logging.error(f"Ошибка при создании клана: {e}")
            
            # Определяем тип ошибки для более информативного сообщения
            if "UNIQUE constraint failed: clans.name" in str(e):
                error_description = f"Клан с именем **{self.name.value}** уже существует! Выберите другое имя."
            elif "UNIQUE constraint failed" in str(e):
                error_description = "Произошла ошибка уникальности данных. Возможно, некоторые элементы уже существуют."
            else:
                error_description = f"Произошла ошибка при создании клана:\n```{str(e)}```"
            
            embed = create_embed(
                title="❌ Ошибка",
                description=error_description,
                color=EmbedColors.ERROR
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

class CreateClanButton(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
    
    @ui.button(label="Создать клан", style=discord.ButtonStyle.primary, emoji="🏰", custom_id="clan_create_button")
    async def create_clan_button(self, interaction: discord.Interaction, button: ui.Button):
        # Проверяем, что пользователь не состоит в клане
        user_clan = check_user_in_clan(interaction.user, interaction.guild)
        if user_clan:
            embed = create_embed(
                title="❌ Ошибка",
                description="Вы уже состоите в клане!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Проверяем баланс
        account = get_or_create_account(interaction.user.id, interaction.guild.id)
        cash = account[0]  # Первый элемент кортежа - cash
        if cash < settings.CLAN_CREATE_COST:
            embed = create_embed(
                title="❌ Недостаточно средств",
                description=f"Для создания клана нужно {settings.CLAN_CREATE_COST} {settings.ECONOMY_SYMBOL}",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Открываем модальное окно
        modal = CreateClanModal()
        await interaction.response.send_modal(modal)

class ClanEmojiModal(ui.Modal, title="Изменить эмодзи клана"):
    def __init__(self, clan_id: int):
        super().__init__()
        self.clan_id = clan_id
        
    emoji = ui.TextInput(
        label="Эмодзи клана",
        placeholder="Например: 🛡️ или :zap: или :fire:",
        max_length=30,
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        clan = get_clan_by_id(self.clan_id)
        if not clan:
            embed = create_embed(
                title="❌ Ошибка",
                description="Клан не найден!",
                color=EmbedColors.ERROR
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Проверяем права владельца
        if clan['owner_id'] != interaction.user.id:
            embed = create_embed(
                title="❌ Ошибка",
                description="Только владелец клана может управлять им!",
                color=EmbedColors.ERROR
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        try:
            # Преобразуем Discord код эмодзи в Unicode
            new_emoji = convert_emoji(self.emoji.value)
            old_emoji = clan.get('emoji', '🛡️')
            logging.info(f"Изменение эмодзи клана {self.clan_id}: '{old_emoji}' -> '{new_emoji}'")
            
            conversion_note = ""
            if self.emoji.value != new_emoji:
                conversion_note = f"\n💡 `{self.emoji.value}` → {new_emoji}"
            
            # Обновляем эмодзи в базе данных
            update_clan_info(self.clan_id, emoji=new_emoji)
            logging.info(f"✅ Эмодзи обновлена в БД для клана {self.clan_id}")
            
            # Обновляем названия каналов с задержками
            clan_name = clan['name']
            
            # Обновляем текстовый канал
            text_channel = interaction.guild.get_channel(clan['text_channel_id'])
            if text_channel:
                new_text_name = f"{new_emoji}-{clan_name.lower().replace(' ', '-')}-clnx"
                logging.info(f"📝 Обновляем текстовый канал: {new_text_name}")
                await text_channel.edit(name=new_text_name)
                await asyncio.sleep(1)  # Задержка для избежания rate limit
            
            # Обновляем все голосовые каналы с нумерацией 1, 2, 3...
            voice_channels = get_clan_voice_channels(self.clan_id)
            user_limit = clan['max_members']
            
            for i, channel_id in enumerate(voice_channels):
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    channel_number = i + 1  # Нумерация начинается с 1
                    new_name = f"{new_emoji} ・ {clan_name} {channel_number}"
                    logging.info(f"🔊 Обновляем голосовой канал {channel_number}: {new_name} (лимит: {user_limit})")
                    await channel.edit(name=new_name, user_limit=user_limit)
                    await asyncio.sleep(1)  # Задержка для избежания rate limit
            
            # Уведомляем владельца об успехе
            embed = create_embed(
                title="✅ Эмодзи изменена",
                description=f"Эмодзи клана успешно обновлена!\n\n"
                           f"**Старая эмодзи:** {old_emoji}\n"
                           f"**Новая эмодзи:** {new_emoji}{conversion_note}",
                color=EmbedColors.SUCCESS
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logging.error(f"Ошибка при изменении эмодзи клана: {e}")
            embed = create_embed(
                title="❌ Ошибка",
                description=f"Произошла ошибка при изменении эмодзи:\n```{str(e)}```",
                color=EmbedColors.ERROR
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

class ClanDeputyModal(ui.Modal, title="Назначить заместителя"):
    def __init__(self, clan_id: int):
        super().__init__()
        self.clan_id = clan_id
        
    user_mention = ui.TextInput(
        label="Участник клана",
        placeholder="Упомяните участника (@пользователь) или введите ID",
        max_length=100,
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        clan = get_clan_by_id(self.clan_id)
        if not clan:
            embed = create_embed(
                title="❌ Ошибка",
                description="Клан не найден!",
                color=EmbedColors.ERROR
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Проверяем права владельца
        if clan['owner_id'] != interaction.user.id:
            embed = create_embed(
                title="❌ Ошибка",
                description="Только владелец клана может назначать заместителей!",
                color=EmbedColors.ERROR
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        try:
            # Пытаемся извлечь ID пользователя из упоминания или текста
            user_input = self.user_mention.value.strip()
            user_id = None
            
            # Проверяем формат упоминания <@123456789>
            if user_input.startswith('<@') and user_input.endswith('>'):
                user_id = int(user_input.strip('<@!>'))
            # Проверяем формат числа
            elif user_input.isdigit():
                user_id = int(user_input)
            else:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Неверный формат! Упомяните пользователя (@пользователь) или введите его ID.",
                    color=EmbedColors.ERROR
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Проверяем, что пользователь не владелец
            if user_id == clan['owner_id']:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Владелец клана не может быть заместителем!",
                    color=EmbedColors.ERROR
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Проверяем, что пользователь состоит в клане
            member_role = get_clan_member_role(self.clan_id, user_id)
            if not member_role:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Этот пользователь не состоит в вашем клане!",
                    color=EmbedColors.ERROR
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Проверяем текущую роль
            if member_role == 'deputy':
                embed = create_embed(
                    title="ℹ️ Информация",
                    description=f"<@{user_id}> уже является заместителем клана!",
                    color=EmbedColors.INFO
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Назначаем заместителя
            update_clan_member_role(self.clan_id, user_id, 'deputy')
            
            embed = create_embed(
                title="✅ Заместитель назначен",
                description=f"<@{user_id}> теперь заместитель клана **{clan['name']}**!\n\n"
                           f"Заместитель может:\n"
                           f"• Приглашать новых участников в клан",
                color=EmbedColors.SUCCESS
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Уведомляем нового заместителя
            try:
                user = await interaction.guild.fetch_member(user_id)
                if user:
                    dm_embed = create_embed(
                        title="🎉 Вы назначены заместителем!",
                        description=f"Вы назначены заместителем клана **{clan['name']}**!\n\n"
                                   f"Теперь вы можете приглашать новых участников в клан.",
                        color=EmbedColors.SUCCESS
                    )
                    await user.send(embed=dm_embed)
            except:
                pass  # Если не удалось отправить ЛС, ничего страшного
            
        except ValueError:
            embed = create_embed(
                title="❌ Ошибка",
                description="Неверный формат ID пользователя!",
                color=EmbedColors.ERROR
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logging.error(f"Ошибка при назначении заместителя: {e}")
            embed = create_embed(
                title="❌ Ошибка",
                description=f"Произошла ошибка при назначении заместителя:\n```{str(e)}```",
                color=EmbedColors.ERROR
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

class ClanKickModal(ui.Modal, title="Исключить участника"):
    def __init__(self, clan_id: int):
        super().__init__()
        self.clan_id = clan_id
        
    user_mention = ui.TextInput(
        label="Участник клана",
        placeholder="Упомяните участника (@пользователь) или введите ID",
        max_length=100,
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        clan = get_clan_by_id(self.clan_id)
        if not clan:
            embed = create_embed(
                title="❌ Ошибка",
                description="Клан не найден!",
                color=EmbedColors.ERROR
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Проверяем права владельца
        if clan['owner_id'] != interaction.user.id:
            embed = create_embed(
                title="❌ Ошибка",
                description="Только владелец клана может исключать участников!",
                color=EmbedColors.ERROR
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        try:
            # Пытаемся извлечь ID пользователя из упоминания или текста
            user_input = self.user_mention.value.strip()
            user_id = None
            
            # Проверяем формат упоминания <@123456789>
            if user_input.startswith('<@') and user_input.endswith('>'):
                user_id = int(user_input.strip('<@!>'))
            # Проверяем формат числа
            elif user_input.isdigit():
                user_id = int(user_input)
            else:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Неверный формат! Упомяните пользователя (@пользователь) или введите его ID.",
                    color=EmbedColors.ERROR
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Проверяем, что пользователь не владелец
            if user_id == clan['owner_id']:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Владелец клана не может быть исключен!",
                    color=EmbedColors.ERROR
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Проверяем, что пользователь состоит в клане
            member_role = get_clan_member_role(self.clan_id, user_id)
            if not member_role:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Этот пользователь не состоит в вашем клане!",
                    color=EmbedColors.ERROR
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Исключаем пользователя из клана
            remove_clan_member(self.clan_id, user_id)
            
            # Убираем роль клана
            try:
                member = await interaction.guild.fetch_member(user_id)
                if member:
                    role = interaction.guild.get_role(clan['role_id'])
                    if role:
                        await member.remove_roles(role)
            except:
                pass  # Если не удалось убрать роль, ничего страшного
            
            embed = create_embed(
                title="✅ Участник исключен",
                description=f"<@{user_id}> исключен из клана **{clan['name']}**!",
                color=EmbedColors.SUCCESS
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Уведомляем исключенного пользователя
            try:
                user = await interaction.guild.fetch_member(user_id)
                if user:
                    dm_embed = create_embed(
                        title="🚫 Вы исключены из клана",
                        description=f"Вы были исключены из клана **{clan['name']}** владельцем <@{interaction.user.id}>.",
                        color=EmbedColors.ERROR
                    )
                    await user.send(embed=dm_embed)
            except:
                pass  # Если не удалось отправить ЛС, ничего страшного
            
        except ValueError:
            embed = create_embed(
                title="❌ Ошибка",
                description="Неверный формат ID пользователя!",
                color=EmbedColors.ERROR
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logging.error(f"Ошибка при исключении участника: {e}")
            embed = create_embed(
                title="❌ Ошибка",
                description=f"Произошла ошибка при исключении участника:\n```{str(e)}```",
                color=EmbedColors.ERROR
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

class ClanManagementModal(ui.Modal, title="Управление кланом"):
    def __init__(self, clan_id: int, field: str):
        super().__init__()
        self.clan_id = clan_id
        self.field = field
        
    name = ui.TextInput(
        label="Название клана",
        placeholder="Введите новое название...",
        max_length=32,
        required=False
    )
    
    description = ui.TextInput(
        label="Описание клана",
        placeholder="Введите новое описание...",
        max_length=200,
        required=False,
        style=discord.TextStyle.paragraph
    )
    
    color = ui.TextInput(
        label="Цвет клана (hex код)",
        placeholder="Например: #FF0000",
        max_length=7,
        required=False
    )
    
    avatar = ui.TextInput(
        label="Аватар клана (URL изображения)",
        placeholder="Ссылка на изображение (необязательно)",
        max_length=200,
        required=False
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        clan = get_clan_by_id(self.clan_id)
        if not clan:
            embed = create_embed(
                title="❌ Ошибка",
                description="Клан не найден!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Проверяем права владельца
        if clan['owner_id'] != interaction.user.id:
            embed = create_embed(
                title="❌ Ошибка",
                description="Только владелец клана может управлять им!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        updates = {}
        
        if self.name.value and self.name.value != clan['name']:
            # Проверяем, что название не занято
            existing_clan = get_clan_by_name(self.name.value)
            if existing_clan and existing_clan['id'] != self.clan_id:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Клан с таким названием уже существует!",
                    color=EmbedColors.ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            updates['name'] = self.name.value
        
        if self.description.value:
            updates['description'] = self.description.value
        
        if self.color.value:
            try:
                color_hex = self.color.value.lstrip('#')
                color_int = int(color_hex, 16)
                updates['color'] = color_int
            except ValueError:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Неверный формат цвета! Используйте hex код (например: #FF0000)",
                    color=EmbedColors.ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
        
        if self.avatar.value:
            updates['avatar_url'] = self.avatar.value
        
        if updates:
            # Обновляем в базе данных
            update_clan_info(
                self.clan_id,
                name=updates.get('name'),
                description=updates.get('description'),
                color=updates.get('color'),
                avatar_url=updates.get('avatar_url')
            )
            
            # Обновляем роль
            if 'name' in updates or 'color' in updates:
                role = interaction.guild.get_role(clan['role_id'])
                if role:
                    new_name = f"{updates.get('name', clan['name'])} clxn"
                    new_color = discord.Color(updates.get('color', clan['color']))
                    await role.edit(name=new_name, color=new_color)
                    await asyncio.sleep(1)  # Задержка для избежания rate limit
            
            # Обновляем названия каналов
            if 'name' in updates:
                new_clan_name = updates.get('name', clan['name'])
                clan_emoji = clan.get('emoji', '🛡️')
                
                logging.info(f"🔄 Обновляем каналы клана. Эмодзи: {clan_emoji}")
                
                # Обновляем текстовый канал - формат: эмодзи-название клана-clnx
                text_channel = interaction.guild.get_channel(clan['text_channel_id'])
                if text_channel:
                    new_text_name = f"{clan_emoji}-{new_clan_name.lower().replace(' ', '-')}-clnx"
                    logging.info(f"📝 Обновляем текстовый канал: {new_text_name}")
                    await text_channel.edit(name=new_text_name)
                    await asyncio.sleep(1)  # Задержка для избежания rate limit
                
                # Обновляем все голосовые каналы с нумерацией 1, 2, 3...
                voice_channels = get_clan_voice_channels(self.clan_id)
                user_limit = clan['max_members']
                
                for i, channel_id in enumerate(voice_channels):
                    channel = interaction.guild.get_channel(channel_id)
                    if channel:
                        channel_number = i + 1  # Нумерация начинается с 1
                        new_name = f"{clan_emoji} ・ {new_clan_name} {channel_number}"
                        logging.info(f"🔊 Обновляем голосовой канал {channel_number}: {new_name} (лимит: {user_limit})")
                        await channel.edit(name=new_name, user_limit=user_limit)
                        await asyncio.sleep(1)  # Задержка для избежания rate limit
            
            embed = create_embed(
                title="✅ Клан обновлен",
                description="Информация о клане успешно обновлена!",
                color=EmbedColors.SUCCESS
            )
        else:
            embed = create_embed(
                title="ℹ️ Ничего не изменено",
                description="Вы не внесли никаких изменений.",
                color=EmbedColors.INFO
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class ClanManagementView(ui.View):
    def __init__(self, clan_id: int, bot):
        super().__init__(timeout=300)
        self.clan_id = clan_id
        self.bot = bot
    
    @ui.button(style=discord.ButtonStyle.secondary, emoji="✏️")
    async def edit_info(self, interaction: discord.Interaction, button: ui.Button):
        clan = get_clan_by_id(self.clan_id)
        if not clan:
            embed = create_embed(
                title="❌ Ошибка",
                description="Клан не найден!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Отладочная информация
        logging.info(f"Проверка прав: user_id={interaction.user.id}, owner_id={clan['owner_id']}")
        
        if clan['owner_id'] != interaction.user.id:
            embed = create_embed(
                title="❌ Ошибка",
                description=f"Только владелец клана может управлять им!\n"
                           f"Владелец: <@{clan['owner_id']}>\n"
                           f"Вы: <@{interaction.user.id}>",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        modal = ClanManagementModal(self.clan_id, "info")
        await interaction.response.send_modal(modal)
    
    @ui.button(style=discord.ButtonStyle.secondary, emoji="👥")
    async def manage_members(self, interaction: discord.Interaction, button: ui.Button):
        clan = get_clan_by_id(self.clan_id)
        if not clan or clan['owner_id'] != interaction.user.id:
            embed = create_embed(
                title="❌ Ошибка",
                description="Только владелец клана может управлять им!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Получаем список участников
        members = get_clan_members(self.clan_id)
        
        embed = create_embed(
            title=f"👥 Участники клана {clan['name']}",
            description=f"Всего участников: {len(members)}/{clan['max_members']}",
            color=clan['color']
        )
        
        member_list = []
        for member in members:
            user = self.bot.get_user(member['user_id'])
            if member['role'] == 'owner':
                role_emoji = "👑"
            elif member['role'] == 'deputy':
                role_emoji = "⭐"
            else:
                role_emoji = "👤"
            member_list.append(f"{role_emoji} {user.mention if user else 'Неизвестный пользователь'}")
        
        if member_list:
            embed.add_field(
                name="Список участников",
                value="\n".join(member_list),
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @ui.button(style=discord.ButtonStyle.secondary, emoji="📈")
    async def buy_slots(self, interaction: discord.Interaction, button: ui.Button):
        clan = get_clan_by_id(self.clan_id)
        if not clan or clan['owner_id'] != interaction.user.id:
            embed = create_embed(
                title="❌ Ошибка",
                description="Только владелец клана может управлять им!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Проверяем максимальное количество слотов
        if clan['max_members'] >= settings.CLAN_MAX_MEMBER_SLOTS:
            embed = create_embed(
                title="❌ Ошибка",
                description=f"Достигнуто максимальное количество слотов ({settings.CLAN_MAX_MEMBER_SLOTS})!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Проверяем баланс
        account = get_or_create_account(interaction.user.id, interaction.guild.id)
        cash = account[0]  # Первый элемент кортежа - cash
        if cash < settings.CLAN_MEMBER_SLOT_COST:
            embed = create_embed(
                title="❌ Недостаточно средств",
                description=f"Для покупки слотов нужно {settings.CLAN_MEMBER_SLOT_COST} {settings.ECONOMY_SYMBOL}",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Показываем подтверждение оплаты
        embed = create_embed(
            title="💰 Подтверждение покупки",
            description=f"Вы хотите купить 10 слотов для участников?\n\n"
                       f"💰 Стоимость: {settings.CLAN_MEMBER_SLOT_COST} {settings.ECONOMY_SYMBOL}\n"
                       f"👥 Текущий лимит: {clan['max_members']}\n"
                       f"👥 Новый лимит: {min(clan['max_members'] + 10, settings.CLAN_MAX_MEMBER_SLOTS)}",
            color=EmbedColors.WARNING
        )
        
        view = PaymentConfirmationView(
            self.clan_id, 
            "slots", 
            settings.CLAN_MEMBER_SLOT_COST,
            self.bot
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @ui.button(style=discord.ButtonStyle.secondary, emoji="🔊")
    async def buy_voice_channel(self, interaction: discord.Interaction, button: ui.Button):
        clan = get_clan_by_id(self.clan_id)
        if not clan or clan['owner_id'] != interaction.user.id:
            embed = create_embed(
                title="❌ Ошибка",
                description="Только владелец клана может управлять им!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Проверяем максимальное количество голосовых каналов
        if clan['voice_channels_count'] >= settings.CLAN_MAX_VOICE_CHANNELS:
            embed = create_embed(
                title="❌ Ошибка",
                description=f"Достигнуто максимальное количество голосовых каналов ({settings.CLAN_MAX_VOICE_CHANNELS})!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Показываем подтверждение оплаты
        embed = create_embed(
            title="💰 Подтверждение покупки",
            description=f"Вы хотите купить дополнительный голосовой канал?\n\n"
                       f"💰 Стоимость: {settings.CLAN_VOICE_CHANNEL_COST} {settings.ECONOMY_SYMBOL}\n"
                       f"🔊 Текущих каналов: {clan['voice_channels_count']}\n"
                       f"🔊 Новое количество: {clan['voice_channels_count'] + 1}",
            color=EmbedColors.WARNING
        )
        
        view = PaymentConfirmationView(
            self.clan_id, 
            "voice", 
            settings.CLAN_VOICE_CHANNEL_COST,
            self.bot
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @ui.button(style=discord.ButtonStyle.secondary, emoji="😀")
    async def change_emoji(self, interaction: discord.Interaction, button: ui.Button):
        clan = get_clan_by_id(self.clan_id)
        if not clan or clan['owner_id'] != interaction.user.id:
            embed = create_embed(
                title="❌ Ошибка",
                description="Только владелец клана может управлять им!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Открываем модальное окно для изменения эмодзи
        modal = ClanEmojiModal(self.clan_id)
        await interaction.response.send_modal(modal)
    
    @ui.button(style=discord.ButtonStyle.secondary, emoji="👤")
    async def assign_deputy(self, interaction: discord.Interaction, button: ui.Button):
        clan = get_clan_by_id(self.clan_id)
        if not clan or clan['owner_id'] != interaction.user.id:
            embed = create_embed(
                title="❌ Ошибка",
                description="Только владелец клана может назначать заместителей!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Открываем модальное окно для назначения заместителя
        modal = ClanDeputyModal(self.clan_id)
        await interaction.response.send_modal(modal)
    
    @ui.button(style=discord.ButtonStyle.secondary, emoji="🚫")
    async def kick_member(self, interaction: discord.Interaction, button: ui.Button):
        clan = get_clan_by_id(self.clan_id)
        if not clan or clan['owner_id'] != interaction.user.id:
            embed = create_embed(
                title="❌ Ошибка",
                description="Только владелец клана может исключать участников!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Открываем модальное окно для исключения участника
        modal = ClanKickModal(self.clan_id)
        await interaction.response.send_modal(modal)
    
    @ui.button(style=discord.ButtonStyle.secondary, emoji="💳")
    async def payment_info(self, interaction: discord.Interaction, button: ui.Button):
        clan = get_clan_by_id(self.clan_id)
        if not clan or clan['owner_id'] != interaction.user.id:
            embed = create_embed(
                title="❌ Ошибка",
                description="Только владелец клана может управлять им!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = create_embed(
            title="💳 Информация о платежах",
            description=f"Информация о платежах клана **{clan['name']}**",
            color=clan['color']
        )
        
        # Добавляем аватар если есть
        if clan.get('avatar_url'):
            embed.set_thumbnail(url=clan['avatar_url'])
        
        embed.add_field(
            name="💳 Ежемесячная плата",
            value=f"{settings.CLAN_MONTHLY_COST} {settings.ECONOMY_SYMBOL}",
            inline=True
        )
        
        embed.add_field(
            name="📅 Последняя оплата",
            value=format_discord_timestamp(clan.get('last_payment'), "Оплата еще не проводилась"),
            inline=True
        )
        
        
        await interaction.response.send_message(embed=embed, ephemeral=True)



class PaymentConfirmationView(ui.View):
    def __init__(self, clan_id: int, purchase_type: str, cost: int, bot):
        super().__init__(timeout=300)
        self.clan_id = clan_id
        self.purchase_type = purchase_type
        self.cost = cost
        self.bot = bot
    
    @ui.button(label="Оплатить", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_payment(self, interaction: discord.Interaction, button: ui.Button):
        # Проверяем баланс
        account = get_or_create_account(interaction.user.id, interaction.guild.id)
        cash = account[0]
        
        if cash < self.cost:
            embed = create_embed(
                title="❌ Недостаточно средств",
                description=f"У вас недостаточно средств для покупки!\n"
                           f"💰 Нужно: {self.cost} {settings.ECONOMY_SYMBOL}\n"
                           f"💰 У вас: {cash} {settings.ECONOMY_SYMBOL}",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            if self.purchase_type == "slots":
                # Покупаем слоты
                add_cash(interaction.user.id, interaction.guild.id, -self.cost)
                clan = get_clan_by_id(self.clan_id)
                new_max_members = min(clan['max_members'] + 10, settings.CLAN_MAX_MEMBER_SLOTS)
                update_clan_max_members(self.clan_id, new_max_members)
                
                # Обновляем лимит участников во всех голосовых каналах
                voice_channels = get_clan_voice_channels(self.clan_id)
                for channel_id in voice_channels:
                    channel = interaction.guild.get_channel(channel_id)
                    if channel:
                        await channel.edit(user_limit=new_max_members)
                        await asyncio.sleep(0.5)  # Небольшая задержка
                
                embed = create_embed(
                    title="✅ Слоты куплены",
                    description=f"Куплено 10 слотов для участников!\n"
                               f"💰 Потрачено: {self.cost} {settings.ECONOMY_SYMBOL}\n"
                               f"👥 Новый лимит: {new_max_members}\n"
                               f"🔊 Лимит участников обновлен во всех голосовых каналах",
                    color=EmbedColors.SUCCESS
                )
                
            elif self.purchase_type == "voice":
                # Покупаем голосовой канал
                add_cash(interaction.user.id, interaction.guild.id, -self.cost)
                clan = get_clan_by_id(self.clan_id)
                
                # Создаем голосовой канал
                voice_category = interaction.guild.get_channel(settings.CLAN_VOICE_CATEGORY_ID)
                if not voice_category:
                    embed = create_embed(
                        title="❌ Ошибка",
                        description="Категория для голосовых каналов кланов не настроена!",
                        color=EmbedColors.ERROR
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                # Формат: эмодзи ・ название клана 1 2 3
                clan_emoji = clan.get('emoji', '🛡️')
                channel_number = clan['voice_channels_count'] + 1  # Следующий номер
                
                channel_name = f"{clan_emoji} ・ {clan['name']} {channel_number}"
                
                voice_channel = await voice_category.create_voice_channel(
                    name=channel_name,
                    user_limit=clan['max_members']
                )
                
                # Настраиваем права доступа
                role = interaction.guild.get_role(clan['role_id'])
                if role:
                    await voice_channel.set_permissions(interaction.guild.default_role, view_channel=True, connect=False)
                    await voice_channel.set_permissions(role, connect=True, speak=True)
                
                # Добавляем в базу данных
                add_clan_voice_channel(self.clan_id, voice_channel.id)
                
                embed = create_embed(
                    title="✅ Голосовой канал создан",
                    description=f"Создан новый голосовой канал для клана!\n"
                               f"💰 Потрачено: {self.cost} {settings.ECONOMY_SYMBOL}\n"
                               f"🔊 Каналов: {clan['voice_channels_count'] + 1}/{settings.CLAN_MAX_VOICE_CHANNELS}",
                    color=EmbedColors.SUCCESS
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logging.error(f"Ошибка при покупке {self.purchase_type}: {e}")
            embed = create_embed(
                title="❌ Ошибка",
                description="Произошла ошибка при покупке. Попробуйте позже.",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @ui.button(label="Отмена", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_payment(self, interaction: discord.Interaction, button: ui.Button):
        embed = create_embed(
            title="❌ Покупка отменена",
            description="Покупка была отменена.",
            color=EmbedColors.INFO
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class ClanInviteView(ui.View):
    def __init__(self, clan_id: int, clan_name: str, inviter_id: int, guild_id: int, bot):
        super().__init__(timeout=300)
        self.clan_id = clan_id
        self.clan_name = clan_name
        self.inviter_id = inviter_id
        self.guild_id = guild_id
        self.bot = bot
    
    @ui.button(label="Принять", style=discord.ButtonStyle.success, emoji="✅")
    async def accept_invite(self, interaction: discord.Interaction, button: ui.Button):
        # Проверяем, что пользователь не в клане
        user_clan = check_user_in_clan(interaction.user, interaction.guild)
        if user_clan:
            embed = create_embed(
                title="❌ Ошибка",
                description="Вы уже состоите в клане!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Получаем информацию о клане
        clan = get_clan_by_id(self.clan_id)
        if not clan:
            embed = create_embed(
                title="❌ Ошибка",
                description="Клан не найден или был удален!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Проверяем лимит участников
        members = get_clan_members(self.clan_id)
        if len(members) >= clan['max_members']:
            embed = create_embed(
                title="❌ Ошибка",
                description=f"Клан **{clan['name']}** заполнен! Максимум участников: {clan['max_members']}",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Добавляем пользователя в клан
        try:
            guild = self.bot.get_guild(self.guild_id)
            if not guild:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Сервер не найден!",
                    color=EmbedColors.ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            member = guild.get_member(interaction.user.id)
            if not member:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Вы не найдены на сервере!",
                    color=EmbedColors.ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Добавляем в базу данных
            if add_clan_member(self.clan_id, interaction.user.id, 'member'):
                # Выдаем роль клана
                role = guild.get_role(clan['role_id'])
                if role:
                    await member.add_roles(role)
                
                embed = create_embed(
                    title="✅ Приглашение принято!",
                    description=f"Вы успешно вступили в клан **{clan['name']}**!\n"
                               f"👥 Участников: {len(members) + 1}/{clan['max_members']}",
                    color=EmbedColors.SUCCESS
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
                # Уведомляем владельца клана
                inviter = self.bot.get_user(self.inviter_id)
                if inviter:
                    try:
                        notify_embed = create_embed(
                            title="✅ Приглашение принято",
                            description=f"{interaction.user.mention} принял приглашение в клан **{clan['name']}**!",
                            color=EmbedColors.SUCCESS
                        )
                        await inviter.send(embed=notify_embed)
                    except discord.Forbidden:
                        pass
                
                # Уведомляем в канале клана
                text_channel = guild.get_channel(clan['text_channel_id'])
                if text_channel:
                    welcome_embed = create_embed(
                        title="👋 Новый участник!",
                        description=f"{interaction.user.mention} присоединился к клану!",
                        color=clan['color']
                    )
                    await text_channel.send(embed=welcome_embed)
                
                # Отключаем кнопки
                for item in self.children:
                    item.disabled = True
                await interaction.message.edit(view=self)
            else:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Не удалось добавить вас в клан. Возможно, вы уже в нем.",
                    color=EmbedColors.ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
        
        except Exception as e:
            logging.error(f"Ошибка при принятии приглашения в клан: {e}")
            embed = create_embed(
                title="❌ Ошибка",
                description=f"Произошла ошибка при добавлении в клан:\n```{str(e)}```",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @ui.button(label="Отклонить", style=discord.ButtonStyle.danger, emoji="❌")
    async def decline_invite(self, interaction: discord.Interaction, button: ui.Button):
        embed = create_embed(
            title="❌ Приглашение отклонено",
            description=f"Вы отклонили приглашение в клан **{self.clan_name}**.",
            color=EmbedColors.INFO
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Уведомляем владельца
        inviter = self.bot.get_user(self.inviter_id)
        if inviter:
            try:
                notify_embed = create_embed(
                    title="❌ Приглашение отклонено",
                    description=f"{interaction.user.mention} отклонил приглашение в клан **{self.clan_name}**.",
                    color=EmbedColors.WARNING
                )
                await inviter.send(embed=notify_embed)
            except discord.Forbidden:
                pass
        
        # Отключаем кнопки
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

def format_discord_timestamp(value: Optional[str], fallback: str = "Неизвестно") -> str:
    if not value:
        return fallback
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        ts = int(dt.timestamp())
        return f"<t:{ts}:F>\n<t:{ts}:R>"
    except (ValueError, TypeError):
        return fallback


class Clans(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.info_message_id = None
        if not getattr(self.bot, "_clan_create_view_registered", False):
            self.bot.add_view(CreateClanButton(self.bot))
            self.bot._clan_create_view_registered = True

    async def cog_load(self):
        """Инициализация при загрузке кога"""
        init_clans_db()
        self.clan_payment_task.start()
        await self.setup_info_channel()
        await self.sync_clan_members()
    
    async def cog_unload(self):
        """Очистка при выгрузке кога"""
        if self.clan_payment_task.is_running():
            self.clan_payment_task.cancel()
    
    async def sync_clan_members(self):
        """Синхронизация участников кланов с ролями Discord"""
        logging.info("🔄 Начинаем синхронизацию участников кланов...")
        
        all_clans = get_all_clans()
        synced_count = 0
        
        # Получаем все гильдии бота
        for guild in self.bot.guilds:
            for clan in all_clans:
                role = guild.get_role(clan['role_id'])
                if not role:
                    continue
                
                # Получаем всех участников с этой ролью
                for member in guild.members:
                    if role in member.roles:
                        # Проверяем, есть ли запись в БД
                        if not get_user_clan(member.id):
                            # Добавляем в БД
                            add_clan_member(clan['id'], member.id, 'member')
                            synced_count += 1
                            logging.info(f"✅ Синхронизирован участник {member.name} ({member.id}) в клан {clan['name']}")
        
        logging.info(f"🔄 Синхронизация завершена. Добавлено {synced_count} участников.")
    
    async def setup_info_channel(self):
        """Настройка информационного канала о кланах"""
        if not settings.CLAN_INFO_CHANNEL_ID:
            logging.warning("CLAN_INFO_CHANNEL_ID не настроен в конфигурации")
            return
        
        try:
            channel = self.bot.get_channel(settings.CLAN_INFO_CHANNEL_ID)
            if not channel:
                logging.error(f"Канал с ID {settings.CLAN_INFO_CHANNEL_ID} не найден! Проверьте правильность ID канала.")
                return
            
            # Проверяем права бота на отправку сообщений в канал
            if not channel.permissions_for(channel.guild.me).send_messages:
                logging.error(f"Бот не имеет прав на отправку сообщений в канал {channel.name} (ID: {settings.CLAN_INFO_CHANNEL_ID})")
                return
            
            logging.info(f"Найден информационный канал: {channel.name} (ID: {settings.CLAN_INFO_CHANNEL_ID})")
            
            # Проверяем, есть ли уже сообщение с информацией
            async for message in channel.history(limit=50):
                if message.author == self.bot.user and message.embeds:
                    embed = message.embeds[0]
                    if embed.title and "Кланы" in embed.title:
                        self.info_message_id = message.id
                        logging.info(f"Найдено существующее информационное сообщение (ID: {self.info_message_id})")
                        await self.update_info_message()
                        return
            
            # Создаем новое сообщение с информацией
            await self.update_info_message()
            
        except Exception as e:
            logging.error(f"Ошибка при настройке информационного канала: {e}")
    
    async def update_info_message(self):
        """Обновление информационного сообщения о кланах"""
        if not settings.CLAN_INFO_CHANNEL_ID:
            logging.warning("CLAN_INFO_CHANNEL_ID не настроен в конфигурации")
            return
        
        channel = self.bot.get_channel(settings.CLAN_INFO_CHANNEL_ID)
        if not channel:
            logging.warning(f"Канал с ID {settings.CLAN_INFO_CHANNEL_ID} не найден")
            return
        
        try:
            # Получаем список всех кланов
            clans = get_all_clans()
            
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
            
            # Создаем кнопку
            view = CreateClanButton(self.bot)
            
            # Используем обычную кнопку без невидимых символов
            
            if self.info_message_id:
                try:
                    message = await channel.fetch_message(self.info_message_id)
                    await message.edit(embed=embed, view=view)
                    logging.info(f"Обновлено информационное сообщение кланов (ID: {self.info_message_id})")
                except discord.NotFound:
                    message = await channel.send(embed=embed, view=view)
                    self.info_message_id = message.id
                    logging.info(f"Создано новое информационное сообщение кланов (ID: {self.info_message_id})")
            else:
                message = await channel.send(embed=embed, view=view)
                self.info_message_id = message.id
                logging.info(f"Создано информационное сообщение кланов (ID: {self.info_message_id})")
                
        except Exception as e:
            logging.error(f"Ошибка при обновлении информационного сообщения кланов: {e}")
    
    @tasks.loop(hours=24)
    async def clan_payment_task(self):
        """Ежедневная проверка и списание оплаты за кланы"""
        clans_for_payment = get_clans_for_payment()
        
        for clan in clans_for_payment:
            try:
                # Получаем владельца клана
                owner = self.bot.get_user(clan['owner_id'])
                if not owner:
                    continue
                
                # Проверяем баланс владельца
                guild_id = None
                related_channel = self.bot.get_channel(clan.get('text_channel_id')) if clan.get('text_channel_id') else None
                if related_channel:
                    guild_id = related_channel.guild.id
                elif settings.TEST_GUILD_ID:
                    guild_id = settings.TEST_GUILD_ID

                if guild_id is None:
                    logging.warning(f"Не удалось определить guild_id для клана {clan['id']}, пропускаем оплату")
                    continue

                account = get_or_create_account(owner.id, guild_id)
                cash = account[0]  # Первый элемент кортежа - cash
                if cash >= settings.CLAN_MONTHLY_COST:
                    # Списываем деньги
                    add_cash(owner.id, guild_id, -settings.CLAN_MONTHLY_COST)
                    update_clan_payment(clan['id'])

                    updated_clan = get_clan_by_id(clan['id']) or clan
                    payment_time = format_discord_timestamp(updated_clan.get('last_payment'), "только что")

                    logging.info(f"Списана оплата за клан {clan['name']} (ID: {clan['id']})")
                    # Уведомляем владельца
                    embed = create_embed(
                        title="💳 Оплата клана",
                        description=(
                            f"С вашего счета списана ежемесячная плата за клан **{clan['name']}**\n"
                            f"💰 Сумма: {settings.CLAN_MONTHLY_COST} {settings.ECONOMY_SYMBOL}\n"
                            f"📅 Оплачено: {payment_time}"
                        ),
                        color=EmbedColors.INFO
                    )
                    try:
                        await owner.send(embed=embed)
                    except discord.Forbidden:
                        logging.warning(f"Не удалось отправить уведомление владельцу {owner} о платеже")
                else:
                    # Недостаточно средств - деактивируем клан
                    deactivate_clan(clan['id'])
                    
                    # Уведомляем владельца
                    embed = create_embed(
                        title="⚠️ Клан деактивирован",
                        description=f"Ваш клан **{clan['name']}** был деактивирован из-за недостатка средств для оплаты.\n"
                                   f"💰 Требуется: {settings.CLAN_MONTHLY_COST} {settings.ECONOMY_SYMBOL}",
                        color=EmbedColors.WARNING
                    )
                    
                    try:
                        await owner.send(embed=embed)
                    except discord.Forbidden:
                        pass
                    
                    logging.warning(f"Клан {clan['name']} (ID: {clan['id']}) деактивирован из-за недостатка средств")
                    
            except Exception as e:
                logging.error(f"Ошибка при обработке оплаты клана {clan['name']}: {e}")
    
    @clan_payment_task.before_loop
    async def before_clan_payment_task(self):
        await self.bot.wait_until_ready()
    
    @app_commands.command(name="clan", description="Управление кланом")
    async def clan_command(self, interaction: discord.Interaction):
        """Основная команда для управления кланом"""
        user_clan = check_user_in_clan(interaction.user, interaction.guild)
        
        if not user_clan:
            embed = create_embed(
                title="❌ Ошибка",
                description="Вы не состоите в клане!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Получаем информацию о клане
        members = get_clan_members(user_clan['id'])
        owner = self.bot.get_user(user_clan['owner_id'])
        
        embed = create_embed(
            title=f"🏰 {user_clan['name']}",
            description=user_clan['description'],
            color=user_clan['color']
        )
        
        # Добавляем аватар если есть
        if user_clan.get('avatar_url'):
            embed.set_thumbnail(url=user_clan['avatar_url'])
        
        embed.add_field(
            name="👑 Владелец",
            value=owner.mention if owner else "Неизвестно",
            inline=True
        )
        
        embed.add_field(
            name="👥 Участников",
            value=f"{len(members)}/{user_clan['max_members']}",
            inline=True
        )
        
        embed.add_field(
            name="🔊 Голосовых каналов",
            value=str(user_clan['voice_channels_count']),
            inline=True
        )
        
        embed.add_field(
            name="📅 Создан",
            value=format_discord_timestamp(user_clan.get('created_at'), "Неизвестно"),
            inline=True
        )
        
        embed.add_field(
            name="💳 Последняя оплата",
            value=format_discord_timestamp(user_clan.get('last_payment'), "Оплата еще не проводилась"),
            inline=True
        )
        
        # Если пользователь владелец клана, показываем панель управления
        if user_clan['owner_id'] == interaction.user.id:
            view = ClanManagementView(user_clan['id'], self.bot)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="clan_manage", description="Панель управления кланом (только для владельцев)")
    async def clan_manage_command(self, interaction: discord.Interaction):
        """Команда для доступа к панели управления кланом"""
        user_clan = check_user_in_clan(interaction.user, interaction.guild)
        
        if not user_clan:
            embed = create_embed(
                title="❌ Ошибка",
                description="Вы не состоите в клане!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if user_clan['owner_id'] != interaction.user.id:
            embed = create_embed(
                title="❌ Ошибка",
                description="Только владелец клана может управлять им!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Создаем эмбед с информацией о клане
        members = get_clan_members(user_clan['id'])
        
        embed = create_embed(
            title=f"🏰 Панель управления кланом {user_clan['name']}",
            description=f"**Описание:** {user_clan['description']}\n"
                       f"**Владелец:** {interaction.user.mention}\n"
                       f"**Участников:** {len(members)}/{user_clan['max_members']}\n"
                       f"**Голосовых каналов:** {user_clan['voice_channels_count']}/{settings.CLAN_MAX_VOICE_CHANNELS}",
            color=user_clan['color']
        )
        
        # Добавляем аватар если есть
        if user_clan.get('avatar_url'):
            embed.set_thumbnail(url=user_clan['avatar_url'])
        
        embed.add_field(
            name="Управление кланом",
            value=f"✏️ - Изменить информацию\n"
                  f"👥 - Управление участниками\n"
                  f"📈 - Купить + 10 слотов за **{settings.CLAN_MEMBER_SLOT_COST}** {settings.ECONOMY_SYMBOL}\n"
                  f"🔊 - Купить голосовой канал за **{settings.CLAN_VOICE_CHANNEL_COST}** {settings.ECONOMY_SYMBOL}\n"
                  f"😀 - Изменить эмодзи клана\n"
                  f"👤 - Назначить заместителя клана\n"
                  f"🚫 - Исключить участника из клана\n"
                  f"💳 - Информация о платежах",
            inline=False
        )
        
        view = ClanManagementView(user_clan['id'], self.bot)
        
        # Отправляем панель управления в текущий канал
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)
    
    @app_commands.command(name="clan_sync", description="Синхронизация участников кланов с ролями Discord (только для администраторов)")
    @app_commands.default_permissions(administrator=True)
    async def clan_sync_command(self, interaction: discord.Interaction):
        """Команда для синхронизации участников кланов"""
        await interaction.response.defer(ephemeral=True)
        
        await self.sync_clan_members()
        
        embed = create_embed(
            title="✅ Синхронизация завершена",
            description="Участники кланов синхронизированы с ролями Discord!",
            color=EmbedColors.SUCCESS
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="clan_setup", description="Настройка информационного канала кланов (только для администраторов)")
    @app_commands.default_permissions(administrator=True)
    async def clan_setup_command(self, interaction: discord.Interaction):
        """Команда для настройки информационного канала кланов"""
        if not settings.CLAN_INFO_CHANNEL_ID:
            embed = create_embed(
                title="❌ Ошибка",
                description="ID информационного канала не настроен в конфигурации!",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Принудительно обновляем информационное сообщение
        await self.update_info_message()
        
        embed = create_embed(
            title="✅ Информационный канал настроен",
            description=f"Эмбед с информацией о кланах отправлен в канал <#{settings.CLAN_INFO_CHANNEL_ID}>",
            color=EmbedColors.SUCCESS
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    

    
    @app_commands.command(name="clan_id", description="Узнать ID клана")
    async def clan_id_command(self, interaction: discord.Interaction):
        """Команда для получения ID клана пользователя"""
        try:
            user_clan = check_user_in_clan(interaction.user, interaction.guild)
            
            if not user_clan:
                embed = create_embed(
                    title="❌ Клан не найден",
                    description="Вы не состоите в клане.",
                    color=EmbedColors.ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            embed = create_embed(
                title="🆔 ID клана",
                description=f"**Название клана:** {user_clan['name']}\n"
                           f"**ID клана:** `{user_clan['id']}`\n"
                           f"**Владелец:** <@{user_clan['owner_id']}>",
                color=EmbedColors.INFO
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logging.error(f"Ошибка при получении ID клана: {e}")
            embed = create_embed(
                title="❌ Ошибка",
                description=f"Произошла ошибка при получении ID клана:\n```{str(e)}```",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="clan_invite", description="Пригласить игрока в клан (владельцы и заместители)")
    @app_commands.describe(member="Участник, которого хотите пригласить в клан")
    async def clan_invite_command(self, interaction: discord.Interaction, member: discord.Member):
        """Команда для приглашения игрока в клан"""
        try:
            # Проверяем, что пользователь состоит в клане
            user_clan = check_user_in_clan(interaction.user, interaction.guild)
            if not user_clan:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Вы не состоите в клане!",
                    color=EmbedColors.ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Проверяем, что пользователь - владелец или заместитель клана
            user_role = get_clan_member_role(user_clan['id'], interaction.user.id)
            if user_role not in ['owner', 'deputy']:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Только владелец или заместитель клана может приглашать игроков!",
                    color=EmbedColors.ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Проверяем, что приглашаемый игрок - не бот
            if member.bot:
                embed = create_embed(
                    title="❌ Ошибка",
                    description="Нельзя приглашать ботов в клан!",
                    color=EmbedColors.ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Проверяем, что приглашаемый игрок не состоит в клане
            member_clan = check_user_in_clan(member, interaction.guild)
            if member_clan:
                embed = create_embed(
                    title="❌ Ошибка",
                    description=f"{member.mention} уже состоит в клане **{member_clan['name']}**!",
                    color=EmbedColors.ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Проверяем лимит участников
            members = get_clan_members(user_clan['id'])
            if len(members) >= user_clan['max_members']:
                embed = create_embed(
                    title="❌ Ошибка",
                    description=f"Клан заполнен! Максимум участников: {user_clan['max_members']}\n"
                               f"Купите дополнительные слоты через `/clan_manage`",
                    color=EmbedColors.ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Отправляем приглашение в ЛС игроку
            clan_emoji = user_clan.get('emoji', '🛡️')
            invite_embed = create_embed(
                title=f"📨 Приглашение в клан!",
                description=f"**{interaction.user.mention}** приглашает вас вступить в клан **{clan_emoji} {user_clan['name']}**!\n\n"
                           f"📝 Описание: {user_clan['description']}\n"
                           f"👥 Участников: {len(members)}/{user_clan['max_members']}\n"
                           f"👑 Владелец: {interaction.user.mention}\n\n"
                           f"Принять приглашение?",
                color=user_clan['color']
            )
            
            # Добавляем аватар клана если есть
            if user_clan.get('avatar_url'):
                invite_embed.set_thumbnail(url=user_clan['avatar_url'])
            
            view = ClanInviteView(
                clan_id=user_clan['id'],
                clan_name=user_clan['name'],
                inviter_id=interaction.user.id,
                guild_id=interaction.guild.id,
                bot=self.bot
            )
            
            try:
                await member.send(embed=invite_embed, view=view)
                
                # Подтверждаем отправку приглашения
                embed = create_embed(
                    title="✅ Приглашение отправлено",
                    description=f"Приглашение в клан **{user_clan['name']}** отправлено игроку {member.mention}!",
                    color=EmbedColors.SUCCESS
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
            except discord.Forbidden:
                embed = create_embed(
                    title="❌ Ошибка",
                    description=f"Не удалось отправить приглашение {member.mention}.\n"
                               f"У пользователя закрыты личные сообщения.",
                    color=EmbedColors.ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
        
        except Exception as e:
            logging.error(f"Ошибка при отправке приглашения в клан: {e}")
            embed = create_embed(
                title="❌ Ошибка",
                description=f"Произошла ошибка при отправке приглашения:\n```{str(e)}```",
                color=EmbedColors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    




async def setup(bot):
    await bot.add_cog(Clans(bot))
