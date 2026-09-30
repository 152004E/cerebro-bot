import os
import tempfile
import logging
import re
import html
import telegram.error
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, TypeHandler

from core.config import TELEGRAM_TOKEN
from core.ai import process_audio_to_text, chat_with_gemini, generate_final_markdown
from core.github import upload_to_obsidian
from core.telemetry import log_success, log_error, get_user_stats, MAX_DAILY_REQUESTS

logger = logging.getLogger("cerebro.bot")

import time

user_requests_minute = []

def get_dynamic_keyboard(latency: float, tokens: int, response_text: str, current_requests: int = 0):
    """Genera el teclado dinámico con métricas en la fila 1 y botón guardar en la fila 2 (condicionado)."""
    global user_requests_minute
    current_time = time.time()
    
    # 1. Limpiar peticiones de hace más de 60 segundos
    user_requests_minute = [t for t in user_requests_minute if current_time - t < 60]
    rpm = len(user_requests_minute)
    
    keyboard = []
    
    # Fila 1: Métricas informativas
    if latency is not None and tokens is not None:
        tokens_left = 250000 - tokens
        if tokens_left < 0: tokens_left = 0
        metrics_text = f"⏱️ {latency:.1f}s | 🧠 Memoria Libre: {tokens_left/1000:.0f}k | ✉️ {MAX_DAILY_REQUESTS - current_requests} msg hoy"
        keyboard.append([InlineKeyboardButton(metrics_text, callback_data='ignore')])
        
    # Fila 2: Botón Guardar (solo si la respuesta es extensa y parece un debate)
    if len(response_text) > 500:
        keyboard.append([InlineKeyboardButton("💾 Guardar Idea en Obsidian", callback_data='save_vault')])
        
    if not keyboard:
        return None
        
    return InlineKeyboardMarkup(keyboard)

def format_for_telegram_html(text: str) -> str:
    """Convierte Markdown estándar al HTML seguro y limpio de Telegram."""
    # 1. Escapamos caracteres HTML para evitar que etiquetas como <twisty-player> rompan el parseo
    text = html.escape(text)
    
    # 2. Reemplazamos viñetas de asterisco por puntos elegantes (Bullet points)
    text = re.sub(r'^\s*\*\s+', '• ', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*-\s+', '• ', text, flags=re.MULTILINE)
    
    # 3. Negritas: **texto** -> <b>texto</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    
    # 4. Código en línea: `codigo` -> <code>codigo</code>
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    
    # 5. Enlaces: [texto](url) -> <a href="url">texto</a>
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = f"@{user.username}" if user.username else user.first_name
    print(f"\n📥 [/start] Comando recibido de {username}")
    
    await update.message.reply_text(
        "🧠 ¡Hola! Soy el Bot de tu Cerebro Digital.\n"
        "Ahora soy tu Asistente de Ideación. Envíame notas de voz o mensajes de texto. "
        "Leeré el contexto de tu bóveda y debatiré contigo para desarrollar tus ideas.\n\n"
        "Cuando hayamos concluido, pulsa el botón 'Guardar' para estructurar la conversación y enviarla a Obsidian.\n"
        "Si quieres cambiar de tema sin guardar, usa el comando /limpiar."
    )

async def cmd_limpiar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    from core.ai import chat_sessions
    if user_id in chat_sessions:
        del chat_sessions[user_id]
        await update.message.reply_text("🧹 Memoria limpiada. ¡Listo para una nueva idea!")
    else:
        await update.message.reply_text("La memoria ya estaba vacía.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = get_user_stats(user_id)
    
    if stats['requests'] >= MAX_DAILY_REQUESTS:
        await update.message.reply_text(f"⚠️ Has alcanzado tu límite de {MAX_DAILY_REQUESTS} respuestas por hoy.")
        return
        
    print(f"📩 ¡Mensaje de texto recibido! Iniciando debate...")
    msg = await update.message.reply_text("🧠 Pensando y consultando la bóveda...")
    
    try:
        raw_text = update.message.text
        user_requests_minute.append(time.time())
        result = chat_with_gemini(user_id, raw_text)
        
        if not result:
            log_error(user_id)
            await msg.edit_text("❌ Hubo un error al comunicarme con Gemini.")
            return
            
        if "error" in result and result["error"] == "rate_limit":
            await msg.edit_text("⚠️ <b>Límite de Google alcanzado (15 pet/min)</b>.\nEl modelo gratuito necesita un respiro. Espera ~30 segundos y vuelve a enviar tu mensaje.", parse_mode='HTML')
            return
            
        log_success(user_id, result["tokens"], result["latency"])
        
        # Limpiamos el texto a formato HTML de Telegram
        html_msg = format_for_telegram_html(result["text"])
        
        # Obtenemos el teclado con las métricas inyectadas y botón condicional
        keyboard = get_dynamic_keyboard(result["latency"], result["tokens"], result["text"], stats['requests'] + 1)
        
        try:
            if keyboard:
                await msg.edit_text(html_msg, reply_markup=keyboard, parse_mode='HTML')
            else:
                await msg.edit_text(html_msg, parse_mode='HTML')
        except telegram.error.BadRequest as e:
            if "parse entities" in str(e).lower():
                print("⚠️ [Telegram HTML Error] Falló el parseo. Enviando sin formato.")
                # Fallback extremo si falla el HTML
                await msg.edit_text(result["text"], reply_markup=keyboard)
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
        await update.message.reply_text(f"⚠️ Has alcanzado tu límite de {MAX_DAILY_REQUESTS} respuestas por hoy.")
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
            
        await msg.edit_text(f"🗣️ <i>Tú dijiste:</i> {html.escape(transcription)}\n\n🧠 Pensando mi respuesta y consultando la bóveda...", parse_mode='HTML')
        
        user_requests_minute.append(time.time())
        result = chat_with_gemini(user_id, transcription)
        
        if not result:
            log_error(user_id)
            await msg.edit_text("❌ Hubo un error de IA al procesar el debate.")
            return
            
        if "error" in result and result["error"] == "rate_limit":
            await msg.edit_text("⚠️ <b>Límite de Google alcanzado (15 pet/min)</b>.\nEl modelo gratuito necesita un respiro. Espera ~30 segundos y vuelve a enviar tu nota de voz.", parse_mode='HTML')
            return
            
        log_success(user_id, result["tokens"], result["latency"])
        
        # Limpiamos el texto a formato HTML
        html_response = format_for_telegram_html(result["text"])
        final_msg = f"🗣️ <i>Tú dijiste: {html.escape(transcription)}</i>\n\n" + html_response
        
        keyboard = get_dynamic_keyboard(result["latency"], result["tokens"], result["text"], stats['requests'] + 1)
        
        try:
            if keyboard:
                await msg.edit_text(final_msg, reply_markup=keyboard, parse_mode='HTML')
            else:
                await msg.edit_text(final_msg, parse_mode='HTML')
        except telegram.error.BadRequest as e:
            if "parse entities" in str(e).lower():
                print("⚠️ [Telegram HTML Error] Falló el parseo. Enviando sin formato.")
                # Fallback extremo
                await msg.edit_text(result["text"], reply_markup=keyboard)
            else:
                raise
            
    except Exception as e:
        print(f"❌ [Error] Excepción en handle_voice: {e}")
        log_error(user_id)
        await msg.edit_text("❌ Error inesperado procesando la nota.")

async def handle_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'ignore':
        return
        
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
        
        await query.edit_message_text(text="🐙 Inyectando resumen en tu repositorio de Obsidian (Vía GitHub)...")
        file_path = upload_to_obsidian(markdown_text)
        
        if file_path:
            await query.edit_message_text(
                text=f"✅ ¡Éxito! La idea desarrollada se guardó en:\n<code>{html.escape(file_path)}</code>", 
                parse_mode='HTML'
            )
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
    app.add_handler(CommandHandler("limpiar", cmd_limpiar))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_button_callback))
    app.add_error_handler(error_handler)
    return app
