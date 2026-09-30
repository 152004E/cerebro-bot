import os
import tempfile
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from core.config import TELEGRAM_TOKEN
from core.ai import process_audio_to_markdown, process_text_to_markdown
from core.github import upload_to_obsidian

logger = logging.getLogger("cerebro.bot")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = f"@{user.username}" if user.username else user.first_name
    print(f"\n📥 [/start] Comando recibido de {username} (ID: {user.id})")
    await update.message.reply_text(
        "🧠 ¡Hola! Soy el Bot de tu Cerebro Digital.\n"
        "Envíame un audio o un texto y lo inyectaré como Markdown en tu bóveda de Obsidian."
    )
    print(f"📤 [/start] Respuesta de bienvenida enviada a {username}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"📩 ¡Mensaje de texto recibido de {update.message.chat.first_name}! Procesando...")
    msg = await update.message.reply_text("🧠 Formateando tu nota de texto con IA...")
    try:
        raw_text = update.message.text
        print("🤖 [IA] Enviando texto a Gemini...")
        markdown_text = process_text_to_markdown(raw_text)
        
        if not markdown_text:
            print("❌ [IA] Falló la generación de Markdown con Gemini")
            await msg.edit_text("❌ Hubo un error de IA al procesar el texto.")
            return
            
        print("✅ [IA] Markdown generado exitosamente:")
        print("--- INICIO NOTA ---")
        print(markdown_text.strip())
        print("--- FIN NOTA ---")

        await msg.edit_text("🐙 Inyectando en tu repositorio de GitHub...")
        print("🐙 [GitHub] Subiendo archivo al repositorio...")
        file_path = upload_to_obsidian(markdown_text)
        
        if file_path:
            print(f"✅ [GitHub] Nota inyectada con éxito en: {file_path}")
            await msg.edit_text(f"✅ ¡Éxito! Tu nota ha sido inyectada en:\n`{file_path}`", parse_mode='Markdown')
        else:
            print("❌ [GitHub] Error subiendo el archivo al repositorio")
            await msg.edit_text("❌ Falló la subida a GitHub.")
            
    except Exception as e:
        print(f"❌ [Error] Excepción en handle_text: {e}")
        await msg.edit_text("❌ Error inesperado procesando la nota.")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"🎙️ ¡Nota de voz recibida de {update.message.chat.first_name}! Procesando...")
    msg = await update.message.reply_text("🎧 Descargando nota de voz...")
    
    try:
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as tmp_file:
            temp_path = tmp_file.name
            
        print(f"⬇️ [Audio] Descargando archivo temporal en: {temp_path}")
        await file.download_to_drive(temp_path)
        print(f"✅ [Audio] Descarga completada ({os.path.getsize(temp_path)} bytes)")

        await msg.edit_text("🧠 Analizando con Inteligencia Artificial...")
        print("🤖 [IA] Subiendo audio y procesando con Gemini 2.5 Flash...")
        markdown_text = process_audio_to_markdown(temp_path)
        
        if os.path.exists(temp_path):
            os.remove(temp_path)
            print("🧹 [Audio] Archivo temporal eliminado")
        
        if not markdown_text:
            print("❌ [IA] Falló la transcripción/formateo de audio con Gemini")
            await msg.edit_text("❌ Hubo un error de IA al procesar el audio.")
            return
            
        print("✅ [IA] Transcripción y Markdown generados exitosamente:")
        print("--- INICIO NOTA ---")
        print(markdown_text.strip())
        print("--- FIN NOTA ---")

        await msg.edit_text("🐙 Inyectando en tu repositorio de GitHub...")
        print("🐙 [GitHub] Subiendo archivo al repositorio...")
        file_path = upload_to_obsidian(markdown_text)
        
        if file_path:
            print(f"✅ [GitHub] Nota inyectada con éxito en: {file_path}")
            await msg.edit_text(f"✅ ¡Éxito! Tu nota ha sido inyectada en:\n`{file_path}`", parse_mode='Markdown')
        else:
            print("❌ [GitHub] Error subiendo el archivo al repositorio")
            await msg.edit_text("❌ Falló la subida a GitHub.")
            
    except Exception as e:
        print(f"❌ [Error] Excepción en handle_voice: {e}")
        await msg.edit_text("❌ Error inesperado procesando la nota.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"⚠️ [Telegram Network/Warning] {context.error}")

from telegram.ext import TypeHandler

async def debug_raw_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"\n🔍 [DEBUG RAW EVENT] Actualización recibida de Telegram!")
    if update.message:
        print(f"   -> Mensaje de: @{update.effective_user.username or update.effective_user.first_name} (ID: {update.effective_user.id})")
        print(f"   -> Tipo: {'Voz' if update.message.voice else 'Texto' if update.message.text else 'Otro'}")
        if update.message.text:
            print(f"   -> Texto: {update.message.text}")

def setup_bot():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    # Handler global prioritario (grupo -1) para ver cualquier evento que llegue
    app.add_handler(TypeHandler(Update, debug_raw_update), group=-1)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)
    return app


