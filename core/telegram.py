from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from core.config import TELEGRAM_TOKEN
from core.ai import process_audio_to_markdown, process_text_to_markdown
from core.github import upload_to_obsidian
import os
import tempfile

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧠 ¡Hola! Soy el Bot de tu Cerebro Digital.\n"
        "Envíame un audio o un texto y lo inyectaré como Markdown en tu bóveda de Obsidian."
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🧠 Formateando tu nota de texto con IA...")
    try:
        markdown_text = process_text_to_markdown(update.message.text)
        
        if not markdown_text:
            await msg.edit_text("❌ Hubo un error de IA al procesar el texto.")
            return
            
        await msg.edit_text("🐙 Inyectando en tu repositorio de GitHub...")
        file_path = upload_to_obsidian(markdown_text)
        
        if file_path:
            await msg.edit_text(f"✅ ¡Éxito! Tu nota ha sido inyectada en:\n`{file_path}`", parse_mode='Markdown')
        else:
            await msg.edit_text("❌ Falló la subida a GitHub.")
            
    except Exception as e:
        print(f"Error en handle_text: {e}")
        await msg.edit_text("❌ Error inesperado procesando la nota.")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🎧 Descargando nota de voz...")
    
    try:
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as tmp_file:
            temp_path = tmp_file.name
            
        await file.download_to_drive(temp_path)
        await msg.edit_text("🧠 Analizando con Inteligencia Artificial...")
        
        markdown_text = process_audio_to_markdown(temp_path)
        os.remove(temp_path)
        
        if not markdown_text:
            await msg.edit_text("❌ Hubo un error de IA al procesar el audio.")
            return
            
        await msg.edit_text("🐙 Inyectando en tu repositorio de GitHub...")
        
        file_path = upload_to_obsidian(markdown_text)
        
        if file_path:
            await msg.edit_text(f"✅ ¡Éxito! Tu nota ha sido inyectada en:\n`{file_path}`", parse_mode='Markdown')
        else:
            await msg.edit_text("❌ Falló la subida a GitHub.")
            
    except Exception as e:
        print(f"Error: {e}")
        await msg.edit_text("❌ Error inesperado procesando la nota.")

def setup_bot():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return app
