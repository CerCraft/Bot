import discord
from datetime import datetime

class EmbedColors:
    INFO = discord.Color.from_str("#45248e")
    ERROR = discord.Color.from_str("#45248e")
    SUCCESS = discord.Color.from_str("#45248e")
    WARNING = discord.Color.from_str("#45248e")
    DEFAULT = discord.Color.from_str("#45248e")

def create_embed(
    title: str = None,
    description: str = None,
    color: discord.Color = EmbedColors.DEFAULT,
    author: discord.Member = None,
) -> discord.Embed:
    """
    Создаёт стандартный эмбед с футером:
    - Футер = аватар + имя автора | время вызова
    """
    embed = discord.Embed(title=title, description=description, color=color)

    if author:
        now = datetime.now().strftime("%H:%M")
        embed.set_footer(
            text=f"{author.display_name} | {now}",
            icon_url=author.display_avatar.url if author.display_avatar else None
        )

    return embed

def create_access_error_embed(author: discord.Member = None) -> discord.Embed:
    """
    Создаёт стандартный эмбед для ошибки доступа
    """
    embed = discord.Embed(
        title="❌ Нет доступа",
        description="У вас нет прав для выполнения этой команды.",
        color=EmbedColors.ERROR
    )
    
    if author:
        now = datetime.now().strftime("%H:%M")
        embed.set_footer(
            text=f"{author.display_name} | {now}",
            icon_url=author.display_avatar.url if author.display_avatar else None
        )
    
    return embed
