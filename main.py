# === KEEP-ALIVE (должен быть первым) ===
import keep_alive
keep_alive.keep_alive()  # запускаем веб-сервер ДО всего остального

# === ОСТАЛЬНЫЕ ИМПОРТЫ ===
import os
import asyncio
import logging
from src.core.bot import NaeratusBot
from src.core.config import settings
from src.database.connection import init_db
from src.database.discipline import init_discipline_db
from src.database.economy import init_economy_db

# === НАСТРОЙКИ ===
os.environ["DISCORD_NO_VOICE"] = "1"  # предотвращает ошибку audioop

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

    bot = NaeratusBot()
    try:
        await bot.start(settings.TOKEN)
    except KeyboardInterrupt:
        logging.warning("🛑 Бот остановлен вручную.")
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
