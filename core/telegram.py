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
        metrics_text = f"⏱️ {latency:.1f}s | 🧠 {tokens_left/1000:.0f}k | ✉️ {MAX_DAILY_REQUESTS - current_requests}/{MAX_DAILY_REQUESTS}"
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
        "Envíame notas de voz o mensajes de texto y debatiremos tus ideas.\n\n"
        "Para ver todo lo que puedo hacer, usa el comando /comandos."
    )

async def cmd_limpiar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    from core.ai import chat_sessions
    if user_id in chat_sessions:
        del chat_sessions[user_id]
        await update.message.reply_text("🧹 Memoria limpiada.")
    else:
        await update.message.reply_text("La memoria ya estaba vacía.")
        
    await start(update, context)

async def cmd_comandos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "🛠️ <b>Comandos Disponibles</b>\n\n"
        "🔸 /comandos - Muestra esta lista de ayuda.\n"
        "🔸 /reintentar - Vuelve a enviar tu último mensaje (útil si hay error 503).\n"
        "🔸 /guardar - Guarda la conversación actual en Obsidian directamente.\n"
        "🔸 /estado - Muestra el estado del sistema, límite de mensajes y archivos indexados.\n"
        "🔸 /limpiar - Borra la memoria del chat actual para empezar una idea nueva.\n"
    )
    await update.message.reply_text(texto, parse_mode='HTML')

async def cmd_reintentar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in last_user_prompts:
        await update.message.reply_text("❌ No hay ningún mensaje anterior para reintentar.")
        return
        
    stats = get_user_stats(user_id)
    if stats['requests'] >= MAX_DAILY_REQUESTS:
        await update.message.reply_text(f"⚠️ Has alcanzado tu límite de {MAX_DAILY_REQUESTS} respuestas por hoy.")
        return

    text = last_user_prompts[user_id]
    msg = await update.message.reply_text("🔄 Reintentando tu último mensaje...\n🧠 Pensando y consultando la bóveda...")
    await execute_gemini_flow(msg, user_id, text)

async def cmd_guardar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = await update.message.reply_text("⏳ Resumiendo la conversación y extrayendo ideas clave...")
    
    result = generate_final_markdown(user_id)
    
    if not result:
        log_error(user_id)
        await msg.edit_text("❌ No se pudo generar el resumen final o la sesión ya expiró.")
        return
        
    log_success(user_id, result["tokens"], result["latency"])
    markdown_text = result["text"]
    
    await msg.edit_text("🐙 Inyectando resumen en tu repositorio de Obsidian (Vía GitHub)...")
    file_path = upload_to_obsidian(markdown_text)
    
    if file_path:
        await msg.edit_text(
            f"✅ ¡Éxito! La idea desarrollada se guardó en:\n<code>{html.escape(file_path)}</code>", 
            parse_mode='HTML'
        )
    else:
        await msg.edit_text("❌ Falló la subida a GitHub.")

async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = get_user_stats(user_id)
    
    import core.rag as rag
    import json
    import os
    
    vault_size = 0
    if os.path.exists(rag.CACHE_FILE):
        try:
            with open(rag.CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                vault_size = len(cache)
        except Exception:
            pass
    
    texto = (
        "📊 <b>Estado del Sistema</b>\n\n"
        f"✉️ <b>Mensajes Hoy:</b> {stats['requests']} / {MAX_DAILY_REQUESTS}\n"
        f"📚 <b>Archivos Indexados (RAG):</b> {vault_size}\n"
        f"🧠 <b>Modelo Activo:</b> gemini-3.5-flash-lite\n"
        f"⚠️ <b>Errores Hoy:</b> {stats.get('errors', 0)}\n"
    )
    await update.message.reply_text(texto, parse_mode='HTML')

last_user_prompts = {}

async def execute_gemini_flow(msg, user_id, text, prefix_html=""):
    """Función central que llama a Gemini y actualiza el mensaje en Telegram."""
    global user_requests_minute
    last_user_prompts[user_id] = text
    
    try:
        user_requests_minute.append(time.time())
        result = chat_with_gemini(user_id, text)
        
        if not result:
            log_error(user_id)
            await msg.edit_text(prefix_html + "❌ Hubo un error al comunicarme con Gemini.", parse_mode='HTML')
            return
            
        if "error" in result and result["error"] == "rate_limit":
            await msg.edit_text(prefix_html + "⚠️ <b>Límite de Google alcanzado (15 pet/min)</b>.\nEspera ~30 segundos y vuelve a intentar.", parse_mode='HTML')
            return
            
        log_success(user_id, result["tokens"], result["latency"])
        stats = get_user_stats(user_id)
        
        html_response = format_for_telegram_html(result["text"])
        final_msg = prefix_html + html_response
        
        keyboard = get_dynamic_keyboard(result["latency"], result["tokens"], result["text"], stats['requests'])
        
        try:
            if keyboard:
                await msg.edit_text(final_msg, reply_markup=keyboard, parse_mode='HTML')
            else:
                await msg.edit_text(final_msg, parse_mode='HTML')
        except telegram.error.BadRequest as e:
            if "parse entities" in str(e).lower():
                print("⚠️ [Telegram HTML Error] Falló el parseo. Enviando sin formato.")
                await msg.edit_text(result["text"], reply_markup=keyboard)
            else:
                raise
                
    except Exception as e:
        print(f"❌ [Error] Excepción en execute_gemini_flow: {e}")
        log_error(user_id)
        await msg.edit_text(prefix_html + "❌ Error inesperado procesando la respuesta.", parse_mode='HTML')

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = get_user_stats(user_id)
    
    if stats['requests'] >= MAX_DAILY_REQUESTS:
        await update.message.reply_text(f"⚠️ Has alcanzado tu límite de {MAX_DAILY_REQUESTS} respuestas por hoy.")
        return
        
    print(f"📩 ¡Mensaje de texto recibido! Iniciando debate...")
    msg = await update.message.reply_text("🧠 Pensando y consultando la bóveda...")
    raw_text = update.message.text
    
    await execute_gemini_flow(msg, user_id, raw_text)

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
            
        prefix_html = f"🗣️ <i>Tú dijiste: {html.escape(transcription)}</i>\n\n"
        await msg.edit_text(prefix_html + "🧠 Pensando mi respuesta y consultando la bóveda...", parse_mode='HTML')
        
        await execute_gemini_flow(msg, user_id, transcription, prefix_html)
            
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
    app.add_handler(CommandHandler("comandos", cmd_comandos))
    app.add_handler(CommandHandler("reintentar", cmd_reintentar))
    app.add_handler(CommandHandler("guardar", cmd_guardar))
    app.add_handler(CommandHandler("estado", cmd_estado))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_button_callback))
    app.add_error_handler(error_handler)
    return app
