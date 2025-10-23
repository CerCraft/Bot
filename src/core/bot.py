# src/core/bot.py
import discord
from discord.ext import commands
from src.core.config import settings
import logging
import asyncio


class NaeratusBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(
            command_prefix=commands.when_mentioned_or(settings.PREFIX),
            intents=intents,
        )

    async def setup_hook(self):
        """Автоматически загружаем коги и синхронизируем слэш-команды"""
        for ext in settings.EXTENSIONS:
            try:
                await self.load_extension(ext)
                logging.info(f"✅ Ког загружен: {ext}")
            except Exception as e:
                logging.error(f"❌ Ошибка при загрузке {ext}: {e}")

        logging.info("🧠 Все коги успешно загружены.")

        if settings.TEST_GUILD_ID:
            guild = discord.Object(id=settings.TEST_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logging.info(f"✅ Слэш-команды синхронизированы для гильдии {guild.id}")

    async def on_ready(self):
        logging.info(f"🤖 Бот запущен как {self.user} (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Game(name="/help"),
            status=discord.Status.online,
        )

    async def close(self):
        """Корректное завершение работы"""
        logging.info("⏳ Отключение бота...")
        await super().close()
        await asyncio.sleep(0.2)
        logging.info("✅ Бот корректно остановлен.")
