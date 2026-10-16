from typing import Any
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, CallbackQueryHandler, TypeHandler
)

from core.config import TELEGRAM_TOKEN
from core.telegram.state import user_modes, trivia_options, user_requests_minute, last_user_prompts
from core.telegram.commands import (
    start, cmd_salir, cmd_limpiar, cmd_comandos,
    cmd_reintentar, cmd_guardar, cmd_estado, cmd_searchs
)
from core.telegram.handlers import handle_voice, handle_text
from core.telegram.callbacks import handle_button_callback

async def error_handler(update: object, context: Any) -> None:
    print(f"⚠️ [Telegram Network/Warning] {context.error}")

async def debug_raw_update(update: Update, context: Any) -> None:
    if update.message:
        print(f"🔍 [DEBUG] Evento de mensaje recibido.")

def setup_bot() -> Application:
    """Configura y registra todos los manejadores del bot de Telegram."""
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(TypeHandler(Update, debug_raw_update), group=-1)
    
    # Comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("salir", cmd_salir))
    app.add_handler(CommandHandler("limpiar", cmd_limpiar))
    app.add_handler(CommandHandler("comandos", cmd_comandos))
    app.add_handler(CommandHandler("reintentar", cmd_reintentar))
    app.add_handler(CommandHandler("guardar", cmd_guardar))
    app.add_handler(CommandHandler("estado", cmd_estado))
    app.add_handler(CommandHandler("searchs", cmd_searchs))
    
    # Mensajes de voz y texto
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Botones Interactivos
    app.add_handler(CallbackQueryHandler(handle_button_callback))
    
    app.add_error_handler(error_handler)
    return app

__all__ = [
    "setup_bot",
    "user_modes",
    "trivia_options",
    "user_requests_minute",
    "last_user_prompts"
]
