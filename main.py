import os
os.environ["DISCORD_NO_VOICE"] = "1"

# === ИМПОРТЫ ===
import asyncio
import logging
from aiohttp import web  # ← добавили aiohttp

from src.core.bot import NaeratusBot
from src.core.config import settings
from src.database.connection import init_db
from src.database.discipline import init_discipline_db
from src.database.economy import init_economy_db

# === ВЕБ-СЕРВЕР ДЛЯ UPTIMEROBOT ===
async def health_check(request):
    return web.Response(text="Бот жив! 💚")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    # Replit требует порт 8080
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    logging.info("🌐 Веб-сервер запущен на порту 8080 для UptimeRobot")

# === ОСНОВНОЙ ЗАПУСК ===
async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.info("🚀 Запуск бота...")

    init_db()
    init_discipline_db()
    init_economy_db()

    # Запускаем веб-сервер в фоне
    asyncio.create_task(start_web_server())

    bot = NaeratusBot()
    try:
        await bot.start(settings.TOKEN)
    except KeyboardInterrupt:
        logging.warning("🛑 Бот остановлен вручную.")
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
