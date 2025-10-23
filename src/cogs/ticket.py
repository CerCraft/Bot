# src/cogs/ticket.py
import discord
from discord.ext import commands
from discord import app_commands
from src.core.config import settings
from src.database.tickets import ticket_db
import asyncio
import random
import string
from typing import Optional

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        """Загружаем persistent views при загрузке кога"""
        self.bot.add_view(StaffApplicationView())
        self.bot.add_view(SupportTicketView())
        self.bot.add_view(CloseTicketView())

    def generate_ticket_id(self) -> str:
        """Генерирует уникальный ID для тикета из базы данных"""
        return ticket_db.get_next_ticket_number()

    @commands.command(name="ticket")
    async def ticket_command(self, ctx, action: str = None):
        """Префиксная команда для управления тикетами"""
        if action == "staff":
            await self.send_staff_application_embed(ctx)
        elif action == "support":
            await self.send_support_embed(ctx)
        else:
            embed = discord.Embed(
                title="🎫 Тикет-система",
                description="Доступные команды:",
                color=0x00ff00
            )
            embed.add_field(
                name="!ticket staff",
                value="Отправить эмбед для заявки в стафф",
                inline=False
            )
            embed.add_field(
                name="!ticket support", 
                value="Отправить эмбед для техподдержки",
                inline=False
            )
            await ctx.send(embed=embed)

    async def send_staff_application_embed(self, ctx):
        """Отправляет эмбед для заявки в стафф"""
        embed = discord.Embed(
            title="🎯 Набор в Стафф",
            description="Наш Стафф\n:8003whitecrystal: Вышка:\n:17584arrow: Main Staff — руководство.\n:17584arrow: Administrator — главное, но не высшее звено ответственности и полномочий.\n:17584arrow: Curator — лучшие в своем деле.\n:17584arrow: Developer — разработчики собственных ботов.\n\n:33923whitefeather: Активный набор:\n:17584arrow: Moderator — знают что хорошо, а что плохо.\n:17584arrow: Designer — визуальная составляющая сервера.\n:17584arrow: Helper — помощь по серверу.\n:17584arrow: Creative — Контентная составляющая сервера.\n:17584arrow: Eventsmod & Tribunemod— создатель мероприятий и их ведение.\n:17584arrow: Content Maker — Знают какой контент будет интересен вне сервера.\n:17584arrow: Streamer — активно занимаются ведением Twitch.\n\nМы очень нуждаемся в рабочих лапках, если у тебя есть достаточно свободного времени и хочешь сделать вклад в развитие проекта — можешь смело оставить свою заявку! :Text_Emote_Pack_Purple_Letsgo_D_:",
            color=0x00ff00
        )
        
        if settings.TICKET_STAFF_APPLICATION_IMAGE:
            embed.set_image(url=settings.TICKET_STAFF_APPLICATION_IMAGE)
        
        view = StaffApplicationView()
        await ctx.send(embed=embed, view=view)

    async def send_support_embed(self, ctx):
        """Отправляет эмбед для техподдержки"""
        embed = discord.Embed(
            title="Поддержка",
            description="Если у вас есть вопросы по серверу, жалоба для модераторов, есть идеи для реализации контента или обращение в тех.поддержку - смело открывайте тикет заполнив форму.",
            color=0x0099ff
        )
        
        if settings.TICKET_SUPPORT_IMAGE:
            embed.set_image(url=settings.TICKET_SUPPORT_IMAGE)
        
        view = SupportTicketView()
        await ctx.send(embed=embed, view=view)

    async def create_ticket_thread(self, interaction: discord.Interaction, ticket_type: str, description: str = None, position: str = None):
        """Создает приватную ветку (thread) для тикета"""
        channel = interaction.channel
        user = interaction.user
        
        # Генерируем ID тикета из базы данных
        ticket_id = self.generate_ticket_id()
        
        # Сохраняем информацию в базу данных
        ticket_db.create_ticket(ticket_id, user.id, ticket_type, description, position)
        
        # Создаем приватную ветку
        thread_name = f"{ticket_id.lower()}-{user.name.lower()}"
        ticket_thread = await channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.private_thread,
            invitable=False  # Только модераторы могут добавлять участников
        )
        
        # Добавляем пользователя в ветку
        await ticket_thread.add_user(user)
        
        # Добавляем роли в зависимости от типа тикета
        roles_to_add = []
        if ticket_type == "staff":
            roles_to_add = settings.TICKET_STAFF_APPLICATION_ROLES
        elif ticket_type == "server":
            roles_to_add = settings.TICKET_SERVER_APPEAL_ROLES
        elif ticket_type == "moderation":
            roles_to_add = settings.TICKET_MODERATION_APPEAL_ROLES
        elif ticket_type == "tech_support":
            roles_to_add = settings.TICKET_TECH_SUPPORT_ROLES
        
        # Добавляем пользователей с ролями в ветку
        for role_id in roles_to_add:
            role = interaction.guild.get_role(role_id)
            if role:
                for member in role.members:
                    try:
                        await ticket_thread.add_user(member)
                    except:
                        pass  # Игнорируем ошибки, если пользователь уже в ветке
        
        # Создаем улучшенный эмбед для тикета
        embed = discord.Embed(
            title=f"Номер обращения №{ticket_id}",
            description=f"{user.mention} подал обращение {self.get_ticket_type_name(ticket_type)}",
            color=0x00ff00
        )
        
        # Добавляем аватар пользователя
        embed.set_author(
            name=user.display_name,
            icon_url=user.display_avatar.url
        )
        
        # Добавляем тримбунал (справа сверху)
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        
        if description:
            embed.add_field(
                name="Описание ситуации:",
                value=description,
                inline=False
            )
        
        # Добавляем информацию о должности для заявок в стафф
        if ticket_type == "staff" and position:
            embed.add_field(
                name="Позиция:",
                value=position,
                inline=True
            )
        
        # Отправляем эмбед с кнопкой закрытия
        view = CloseTicketView()
        message = await ticket_thread.send(embed=embed, view=view)
        
        # Упоминаем роли
        if roles_to_add:
            role_mentions = " ".join([f"<@&{role_id}>" for role_id in roles_to_add])
            await ticket_thread.send(f"{role_mentions}")
        
        return ticket_thread

    def get_ticket_type_name(self, ticket_type: str) -> str:
        """Возвращает название типа тикета"""
        type_names = {
            "staff": "заявка в стафф",
            "server": "по серверу",
            "moderation": "для модерации", 
            "tech_support": "в тех. поддержку"
        }
        return type_names.get(ticket_type, "неизвестного типа")

class StaffApplicationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Подать заявку в стафф", style=discord.ButtonStyle.primary, emoji="📝", custom_id="staff_application_button")
    async def staff_application_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = StaffApplicationModal()
        await interaction.response.send_modal(modal)

class SupportTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(
        placeholder="Выберите тип обращения",
        custom_id="support_ticket_select",
        options=[
            discord.SelectOption(
                label="Создать обращение по серверу",
                value="server",
                description="Вопросы и предложения по серверу"
            ),
            discord.SelectOption(
                label="Создать обращение для модерации", 
                value="moderation",
                description="Жалобы и обращения к модераторам"
            ),
            discord.SelectOption(
                label="Создать обращение в тех. поддержку",
                value="tech_support", 
                description="Техническая поддержка"
            )
        ]
    )
    async def support_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        ticket_type = select.values[0]
        
        if ticket_type == "server":
            modal = ServerAppealModal()
        elif ticket_type == "moderation":
            modal = ModerationAppealModal()
        elif ticket_type == "tech_support":
            modal = TechSupportModal()
        else:
            return
        
        await interaction.response.send_modal(modal)

class StaffApplicationModal(discord.ui.Modal, title="Заявка в стафф"):
    def __init__(self):
        super().__init__()
        
        # Поле для выбора должности
        self.add_item(discord.ui.TextInput(
            label="На какую должность подаете заявку",
            placeholder="Например: Moderator, Designer, Helper, Creative...",
            style=discord.TextStyle.short,
            required=True,
            max_length=50
        ))
        
        # Поле для описания
        self.add_item(discord.ui.TextInput(
            label="Опишите суть обращения",
            placeholder="Расскажите о себе, своем опыте и почему хотите стать частью команды...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        ))

    async def on_submit(self, interaction: discord.Interaction):
        position = self.children[0].value
        description = self.children[1].value
        
        # Получаем ког тикет-системы
        ticket_cog = interaction.client.get_cog("TicketSystem")
        if ticket_cog:
            await ticket_cog.create_ticket_thread(interaction, "staff", description, position)
            await interaction.response.send_message("✅ Заявка в стафф успешно создана! Проверьте созданную ветку.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Ошибка: Тикет-система недоступна.", ephemeral=True)

class ServerAppealModal(discord.ui.Modal, title="Обращение по серверу"):
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.TextInput(
            label="Опишите суть обращения",
            placeholder="Опишите ваш вопрос или предложение по серверу...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        ))

    async def on_submit(self, interaction: discord.Interaction):
        description = self.children[0].value
        
        ticket_cog = interaction.client.get_cog("TicketSystem")
        if ticket_cog:
            await ticket_cog.create_ticket_thread(interaction, "server", description)
            await interaction.response.send_message("✅ Обращение по серверу успешно создано! Проверьте созданную ветку.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Ошибка: Тикет-система недоступна.", ephemeral=True)

class ModerationAppealModal(discord.ui.Modal, title="Обращение в модерацию"):
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.TextInput(
            label="Опишите что произошло",
            placeholder="Опишите ситуацию, которая требует внимания модераторов...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        ))

    async def on_submit(self, interaction: discord.Interaction):
        description = self.children[0].value
        
        ticket_cog = interaction.client.get_cog("TicketSystem")
        if ticket_cog:
            await ticket_cog.create_ticket_thread(interaction, "moderation", description)
            await interaction.response.send_message("✅ Обращение для модерации успешно создано! Проверьте созданную ветку.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Ошибка: Тикет-система недоступна.", ephemeral=True)

class TechSupportModal(discord.ui.Modal, title="Тех. поддержка"):
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.TextInput(
            label="Опишите проблему и обстоятельства",
            placeholder="Опишите техническую проблему и обстоятельства, при которых она возникла...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        ))

    async def on_submit(self, interaction: discord.Interaction):
        description = self.children[0].value
        
        ticket_cog = interaction.client.get_cog("TicketSystem")
        if ticket_cog:
            await ticket_cog.create_ticket_thread(interaction, "tech_support", description)
            await interaction.response.send_message("✅ Обращение в тех. поддержку успешно создано! Проверьте созданную ветку.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Ошибка: Тикет-система недоступна.", ephemeral=True)

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Закрыть обращение", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="close_ticket_button")
    async def close_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Проверяем права на закрытие тикета
        if not any(role.id in settings.TICKET_SERVER_APPEAL_ROLES + 
                  settings.TICKET_MODERATION_APPEAL_ROLES + 
                  settings.TICKET_TECH_SUPPORT_ROLES + 
                  settings.TICKET_STAFF_APPLICATION_ROLES for role in interaction.user.roles):
            await interaction.response.send_message("❌ У вас нет прав для закрытия тикетов.", ephemeral=True)
            return
        
        # Создаем подтверждение закрытия
        embed = discord.Embed(
            title="⚠️ Подтверждение закрытия",
            description="Вы уверены, что хотите закрыть это обращение?",
            color=0xff0000
        )
        
        view = ConfirmCloseView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ConfirmCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="Да", style=discord.ButtonStyle.danger, emoji="✅", custom_id="confirm_close_yes")
    async def confirm_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        thread = interaction.channel
        
        # Извлекаем номер тикета из названия ветки
        thread_name = thread.name
        ticket_number = thread_name.split('-')[0].upper() + '-' + thread_name.split('-')[1]
        
        # Обновляем статус в базе данных
        ticket_db.close_ticket(ticket_number)
        
        # Находим пользователя, создавшего тикет (первый пользователь в списке участников ветки)
        ticket_creator = None
        for member in thread.members:
            # Получаем полную информацию о пользователе
            user = interaction.guild.get_member(member.id)
            if user and not user.bot and user != interaction.user:
                ticket_creator = user
                break
        
        # Удаляем пользователя из ветки
        if ticket_creator:
            try:
                await thread.remove_user(ticket_creator)
            except:
                pass
        
        # Отправляем сообщение о закрытии
        embed = discord.Embed(
            title="🔒 Обращение закрыто",
            description=f"Обращение {ticket_number} было закрыто {interaction.user.mention}",
            color=0xff0000
        )
        
        await interaction.response.send_message(embed=embed)
        
        # Удаляем ветку через 5 секунд
        await asyncio.sleep(5)
        try:
            await thread.delete()
        except:
            pass

    @discord.ui.button(label="Нет", style=discord.ButtonStyle.secondary, emoji="❌", custom_id="confirm_close_no")
    async def cancel_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="✅ Отмена",
            description="Закрытие обращения отменено.",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
