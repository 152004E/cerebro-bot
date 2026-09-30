import os
import tempfile
import logging
import telegram.error
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, TypeHandler

from core.config import TELEGRAM_TOKEN
from core.ai import process_audio_to_text, chat_with_gemini, generate_final_markdown
from core.github import upload_to_obsidian
from core.telemetry import log_success, log_error, get_user_stats, MAX_DAILY_REQUESTS

logger = logging.getLogger("cerebro.bot")

def get_save_keyboard():
    """Genera el teclado con el botón de guardado."""
    keyboard = [
        [InlineKeyboardButton("💾 Guardar Idea en la Bóveda", callback_data='save_vault')]
    ]
    return InlineKeyboardMarkup(keyboard)

def format_telemetry_header(latency: float, tokens: int, stats: dict) -> str:
    """Formatea el encabezado con las métricas del mensaje actual y las globales"""
    return (
        f"📊 `[⏱️ {latency:.1f}s | 🪙 {tokens/1000:.1f}k tokens]`\n"
        f"🔄 `[Uso Diario: {stats['requests']}/{MAX_DAILY_REQUESTS}]`\n\n"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = f"@{user.username}" if user.username else user.first_name
    print(f"\n📥 [/start] Comando recibido de {username}")
    
    await update.message.reply_text(
        "🧠 ¡Hola! Soy el Bot de tu Cerebro Digital.\n"
        "Ahora soy tu Asistente de Ideación. Envíame notas de voz o mensajes de texto. "
        "Leeré el contexto de tu bóveda y debatiré contigo para desarrollar tus ideas.\n\n"
        "Cuando hayamos concluido, pulsa el botón 'Guardar' para estructurar la conversación y enviarla a Obsidian."
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = get_user_stats(user_id)
    
    if stats['requests'] >= MAX_DAILY_REQUESTS:
        await update.message.reply_text("⚠️ Has alcanzado tu límite de 1500 respuestas por hoy.")
        return
        
    print(f"📩 ¡Mensaje de texto recibido! Iniciando debate...")
    msg = await update.message.reply_text("🧠 Pensando y consultando la bóveda...")
    
    try:
        raw_text = update.message.text
        result = chat_with_gemini(user_id, raw_text)
        
        if not result:
            log_error(user_id)
            await msg.edit_text("❌ Hubo un error al comunicarme con Gemini.")
            return
            
        log_success(user_id, result["tokens"], result["latency"])
        new_stats = get_user_stats(user_id)
        
        header = format_telemetry_header(result["latency"], result["tokens"], new_stats)
        final_msg = header + result["text"]
        
        try:
            await msg.edit_text(final_msg, reply_markup=get_save_keyboard(), parse_mode='Markdown')
        except telegram.error.BadRequest as e:
            if "parse entities" in str(e).lower():
                print("⚠️ [Telegram Markdown Error] Falló el parseo. Enviando como texto plano.")
                # Fallback sin formato Markdown
                await msg.edit_text(final_msg, reply_markup=get_save_keyboard())
            else:
                raise
        
    except Exception as e:
        print(f"❌ [Error] Excepción en handle_text: {e}")
        log_error(user_id)
        await msg.edit_text("❌ Error inesperado procesando la respuesta.")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = get_user_stats(user_id)
    
    if stats['requests'] >= MAX_DAILY_REQUESTS:
        await update.message.reply_text("⚠️ Has alcanzado tu límite de 1500 respuestas por hoy.")
        return
        
    print(f"🎙️ ¡Nota de voz recibida! Procesando...")
    msg = await update.message.reply_text("🎧 Transcribiendo nota de voz...")
    
    try:
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as tmp_file:
            temp_path = tmp_file.name
            
        await file.download_to_drive(temp_path)
        
        transcription = process_audio_to_text(temp_path)
        
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        if not transcription:
            log_error(user_id)
            await msg.edit_text("❌ Hubo un error transcribiendo el audio.")
            return
            
        await msg.edit_text(f"🗣️ *Tú dijiste:* _{transcription}_\n\n🧠 Pensando mi respuesta y consultando la bóveda...", parse_mode='Markdown')
        
        result = chat_with_gemini(user_id, transcription)
        
        if not result:
            log_error(user_id)
            await msg.edit_text("❌ Hubo un error de IA al procesar el debate.")
            return
            
        log_success(user_id, result["tokens"], result["latency"])
        new_stats = get_user_stats(user_id)
        
        header = format_telemetry_header(result["latency"], result["tokens"], new_stats)
        final_msg = f"🗣️ Tú dijiste: {transcription}\n\n" + header + result["text"]
        
        try:
            await msg.edit_text(final_msg, reply_markup=get_save_keyboard(), parse_mode='Markdown')
        except telegram.error.BadRequest as e:
            if "parse entities" in str(e).lower():
                print("⚠️ [Telegram Markdown Error] Falló el parseo. Enviando como texto plano.")
                # Fallback sin formato Markdown
                await msg.edit_text(final_msg, reply_markup=get_save_keyboard())
            else:
                raise
            
    except Exception as e:
        print(f"❌ [Error] Excepción en handle_voice: {e}")
        log_error(user_id)
        await msg.edit_text("❌ Error inesperado procesando la nota.")

async def handle_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'save_vault':
        user_id = update.effective_user.id
        await query.edit_message_text(text="⏳ Resumiendo la conversación y extrayendo ideas clave...")
        
        result = generate_final_markdown(user_id)
        
        if not result:
            log_error(user_id)
            await query.edit_message_text(text="❌ No se pudo generar el resumen final o la sesión ya expiró.")
            return
            
        log_success(user_id, result["tokens"], result["latency"])
        markdown_text = result["text"]
        
        await query.edit_message_text(text="🐙 Inyectando resumen en tu repositorio de GitHub...")
        file_path = upload_to_obsidian(markdown_text)
        
        if file_path:
            # Siempre se asume seguro porque nosotros construimos este path sin Markdown de Gemini
            await query.edit_message_text(text=f"✅ ¡Éxito! La idea desarrollada se guardó en:\n`{file_path}`", parse_mode='Markdown')
        else:
            await query.edit_message_text(text="❌ Falló la subida a GitHub.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"⚠️ [Telegram Network/Warning] {context.error}")

async def debug_raw_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        print(f"🔍 [DEBUG] Evento de mensaje recibido.")

def setup_bot():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(TypeHandler(Update, debug_raw_update), group=-1)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_button_callback))
    app.add_error_handler(error_handler)
    return app
