from fastapi import FastAPI, Request, Response
from core.telegram import setup_bot
import uvicorn
import asyncio
from telegram import Update
import logging

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

app = FastAPI(title="Cerebro Bot API")
telegram_app = setup_bot()

@app.on_event("startup")
async def on_startup():
    await telegram_app.initialize()
    await telegram_app.start()

@app.post("/webhook")
async def webhook(request: Request):
    try:
        json_data = await request.json()
        update = Update.de_json(json_data, telegram_app.bot)
        asyncio.create_task(telegram_app.process_update(update))
        return Response(status_code=200)
    except Exception as e:
        print(f"Error webhook: {e}")
        return Response(status_code=500)

@app.get("/")
def health_check():
    return {"status": "ok", "message": "Microservicio Bot activo"}

if __name__ == "__main__":
    print("\n" + "="*50)
    print("🚀 [Cerebro Bot] Iniciando en modo Polling (Pruebas Locales)...")
    print("🤖 Bot listo: @Mi_cerebro_magico_bot")
    print("👉 Enlace directo al chat: https://t.me/Mi_cerebro_magico_bot")
    print("👉 Abre Telegram, busca tu bot y envíale /start, un texto o una nota de voz.")
    print("="*50 + "\n")
    telegram_app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


