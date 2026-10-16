import html
import json
import os
from telegram import Update
from telegram.ext import ContextTypes

import core.rag as rag
from core.config import GEMINI_FAST_MODEL, GEMINI_PRO_MODEL
from core.ai import generate_final_markdown, search_internet_ddg, research_with_grok, chat_sessions
from core.github import upload_to_obsidian
from core.telemetry import log_success, log_error, get_user_stats, MAX_DAILY_REQUESTS
from core.telegram.state import user_modes, last_user_prompts
from core.telegram.ui import get_main_keyboard
from core.telegram.handlers import execute_gemini_flow

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando de bienvenida y despliegue del menú principal."""
    user = update.effective_user
    username = f"@{user.username}" if user.username else user.first_name
    print(f"\n📥 [/start] Comando recibido de {username}")
    
    await update.message.reply_text(
        "🧠 ¡Hola! Soy el Bot de tu Cerebro Digital.\n"
        "Envíame notas de voz o mensajes de texto y debatiremos tus ideas.\n\n"
        "Para ver todo lo que puedo hacer, usa el comando /comandos.",
        reply_markup=get_main_keyboard()
    )

async def cmd_limpiar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Borra la memoria del chat actual para iniciar un nuevo debate."""
    user_id = update.effective_user.id
    user_modes[user_id] = "normal"
    if user_id in chat_sessions:
        del chat_sessions[user_id]
        await update.message.reply_text("🧹 Memoria limpiada y modos restablecidos.")
    else:
        await update.message.reply_text("La memoria ya estaba vacía.")
        
    await start(update, context)

async def cmd_salir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sale de Teacher English y regresa al modo normal."""
    user_id = update.effective_user.id
    user_modes[user_id] = "normal"
    await update.message.reply_text(
        "👋 Has salido de <b>Teacher English</b>. De vuelta a tu Cerebro Digital.",
        reply_markup=get_main_keyboard(),
        parse_mode='HTML'
    )

async def cmd_comandos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra la lista de ayuda de comandos disponibles."""
    texto = (
        "🛠️ <b>Comandos Disponibles</b>\n\n"
        "🔸 /comandos - Muestra esta lista de ayuda.\n"
        "🔸 /salir - Sale de Teacher English y regresa al menú principal.\n"
        "🔸 /searchs [tema] - Búsqueda profunda en internet (Reddit y fuentes fiables).\n"
        "🔸 /reintentar - Vuelve a enviar tu último mensaje (útil si hay error 503).\n"
        "🔸 /guardar - Guarda la conversación actual en Obsidian directamente.\n"
        "🔸 /estado - Muestra el estado del sistema, límite de mensajes y archivos indexados.\n"
        "🔸 /limpiar - Borra la memoria del chat actual para empezar una idea nueva.\n"
    )
    await update.message.reply_text(texto, parse_mode='HTML')

async def cmd_reintentar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reintenta el último mensaje enviado por el usuario."""
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

async def cmd_guardar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resume la conversación con Gemini Pro y la sube a la bóveda de Obsidian."""
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

async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra métricas del bot, cuota diaria, archivos RAG y modelos activos."""
    user_id = update.effective_user.id
    stats = get_user_stats(user_id)
    
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
        f"⚡ <b>Modelo Chat / Audio:</b> {GEMINI_FAST_MODEL}\n"
        f"🧠 <b>Modelo Síntesis Bóveda:</b> {GEMINI_PRO_MODEL}\n"
        f"⚠️ <b>Errores Hoy:</b> {stats.get('errors', 0)}\n"
    )
    await update.message.reply_text(texto, parse_mode='HTML')

async def cmd_searchs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Agente de búsqueda e investigación en la web usando DuckDuckGo y Groq."""
    user_id = update.effective_user.id
    query = " ".join(context.args)
    
    if not query:
        await update.message.reply_text("❌ Debes escribir lo que quieres buscar. Ejemplo: /searchs mejores celulares")
        return
        
    msg = await update.message.reply_text(f"🔍 DuckDuckGo está buscando info reciente sobre: {query}...")
    
    search_query = query if "site:" in query else f"{query} site:reddit.com"
    web_context = search_internet_ddg(search_query)
    
    await msg.edit_text("🧠 Groq analizando los resultados...")
    result = research_with_grok(query, web_context)
    
    lat_str = f"{result.get('latency', 0):.2f}s" if 'latency' in result else "N/A"
    footer = f"\n\n<code>[⏱️ Groq: {lat_str}]</code>"
    
    await msg.edit_text(result["text"] + footer, parse_mode='HTML')
