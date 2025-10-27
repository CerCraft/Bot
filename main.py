# === ВСТРОЕННЫЙ HTTP-СЕРВЕР ДЛЯ RENDER (порт 8000) ===
import threading
import http.server
import socketserver
import os
import asyncio
import logging
from src.core.bot import NaeratusBot
from src.core.config import settings
from src.database.connection import init_db
from src.database.discipline import init_discipline_db
from src.database.economy import init_economy_db

# Запуск HTTP-сервера в фоновом потоке
def start_http_server():
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
    with socketserver.TCPServer(("", 8000), Handler) as httpd:
        httpd.serve_forever()

# Запускаем сервер ДО всего остального
threading.Thread(target=start_http_server, daemon=True).start()

# === НАСТРОЙКИ ===
os.environ["DISRING_NO_VOICE"] = "1"  # предотвращает ошибку audioop

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
