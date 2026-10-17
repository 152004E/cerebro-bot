import os
import time
import tempfile
import html
import re
from typing import Optional

from telegram import Update, Message
import telegram.error
from telegram.ext import ContextTypes

from core.ai import process_audio_to_text, chat_with_gemini
from core.telemetry import log_success, log_error, get_user_stats, MAX_DAILY_REQUESTS
from core.telegram.state import user_requests_minute, user_modes, last_user_prompts
from core.telegram.ui import format_for_telegram_html, get_dynamic_keyboard, get_main_keyboard

async def execute_gemini_flow(msg: Message, user_id: int, text: str, prefix_html: str = "", mode: Optional[str] = None) -> None:
    """Función central que llama a Gemini y actualiza el mensaje en Telegram."""
    global user_requests_minute
    last_user_prompts[user_id] = text
    
    active_mode = mode or user_modes.get(user_id, "normal")
    
    try:
        user_requests_minute.append(time.time())
        try:
            await msg.chat.send_action(action="typing")
        except Exception:
            pass
            
        result = chat_with_gemini(user_id, text, mode=active_mode)
        
        if not result:
            log_error(user_id)
            await msg.edit_text(prefix_html + "❌ Hubo un error al comunicarme con Gemini.", parse_mode='HTML')
            return
            
        if "error" in result and result["error"] == "rate_limit":
            await msg.edit_text(prefix_html + "⚠️ <b>Límite de Google alcanzado (15 pet/min)</b>.\nEspera ~30 segundos y vuelve a intentar.", parse_mode='HTML')
            return
            
        log_success(user_id, result["tokens"], result["latency"])
        stats = get_user_stats(user_id)
        
        is_traductor = "[MODO_TRADUCTOR]" in result["text"] or active_mode == "ingles"
        is_tutor = "[MODO_TUTOR]" in result["text"]
        ai_buttons = re.findall(r'\[BOTON:\s*(.*?)\]', result["text"])
        
        clean_text = result["text"].replace("[MODO_TRADUCTOR]", "").replace("[MODO_TUTOR]", "").strip()
        clean_text = re.sub(r'\[BOTON:\s*.*?\]', '', clean_text).strip()
        
        html_response = format_for_telegram_html(clean_text)
        final_msg = prefix_html + html_response
        
        keyboard = get_dynamic_keyboard(result["latency"], result["tokens"], clean_text, stats['requests'], is_traductor, is_tutor, ai_buttons, user_id)
        
        try:
            if keyboard:
                await msg.edit_text(final_msg, reply_markup=keyboard, parse_mode='HTML')
            else:
                await msg.edit_text(final_msg, parse_mode='HTML')
        except telegram.error.BadRequest as e:
            if "parse entities" in str(e).lower():
                print("⚠️ [Telegram HTML Error] Falló el parseo. Enviando sin formato.")
                await msg.edit_text(clean_text, reply_markup=keyboard)
            else:
                raise
                
    except Exception as e:
        print(f"❌ [Error] Excepción en execute_gemini_flow: {e}")
        log_error(user_id)
        await msg.edit_text(prefix_html + "❌ Error inesperado procesando la respuesta.", parse_mode='HTML')

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja los mensajes de texto regulares y enrutamiento según modo."""
    user_id = update.effective_user.id
    stats = get_user_stats(user_id)
    
    if stats['requests'] >= MAX_DAILY_REQUESTS:
        await update.message.reply_text(f"⚠️ Has alcanzado tu límite de {MAX_DAILY_REQUESTS} respuestas por hoy.")
        return

    raw_text = update.message.text.strip()
    
    # 1. Interceptar comandos azules de pista /pista_<slug>
    if raw_text.startswith("/pista_") or raw_text.startswith("/p_"):
        slug = raw_text.split()[0].replace("/pista_", "").replace("/p_", "").strip()
        from core.srs.engine import get_card_by_slug
        from core.srs.games import format_teacher_card
        from core.telegram.ui import get_srs_hint_keyboard
        
        card = get_card_by_slug(slug)
        if card:
            card_text = format_teacher_card(card)
            await update.message.reply_text(card_text, reply_markup=get_srs_hint_keyboard(), parse_mode='HTML')
            return
        else:
            await update.message.reply_text(f"⚠️ No encontré la ficha de vocabulario para '{html.escape(slug)}'.", reply_markup=get_srs_hint_keyboard())
            return

    # 2. Interceptar respuesta de Reto de Escritura SRS si está activo
    from core.telegram.state import user_srs_session
    sess = user_srs_session.get(user_id)
    if sess and sess.get("mode") == "writing" and sess.get("waiting_input") and "current_card" in sess:
        card = sess["current_card"]
        from core.srs.games import evaluate_writing_answer
        from core.srs.engine import record_answer
        from core.telegram.ui import get_srs_feedback_keyboard
        
        is_correct, kind = evaluate_writing_answer(card.word, raw_text)
        if is_correct:
            xp, box, interval = record_answer(user_id, card.slug, "good")
            feedback = (
                f"🎉 <b>¡CORRECTO! (+{xp} XP)</b> ⭐\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Escribiste: <b>{html.escape(raw_text)}</b> ✅\n"
                f"Palabra: <b>{card.word}</b> <code>{card.pronunciation}</code>\n"
                f"📖 <i>{card.meaning}</i>\n\n"
                f"📦 <i>Subió a Caja Leitner {box} (Repaso en {interval} días)</i>"
            )
        else:
            xp, box, interval = record_answer(user_id, card.slug, "again")
            feedback = (
                f"❌ <b>Casi:</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Tú escribiste: <i>{html.escape(raw_text)}</i>\n"
                f"La palabra correcta es: <b>{card.word}</b> <code>{card.pronunciation}</code>\n"
                f"📖 <i>{card.meaning}</i>\n"
                f"💡 Ejemplo: <i>\"{card.example}\"</i>\n\n"
                f"📦 <i>Vuelve a Caja 1 para afianzarla (+{xp} XP)</i>"
            )
        
        sess["waiting_input"] = False
        await update.message.reply_text(feedback, reply_markup=get_srs_feedback_keyboard(), parse_mode='HTML')
        return
        
    # Comprobar si pide salir de Teacher English
    if raw_text.lower() in ["salir", "exit", "volver", "cancelar"]:
        if user_modes.get(user_id) == "ingles":
            user_modes[user_id] = "normal"
            await update.message.reply_text(
                "👋 Has salido de <b>Teacher English</b>. De vuelta a tu Cerebro Digital.",
                reply_markup=get_main_keyboard(),
                parse_mode='HTML'
            )
            return
            
    if user_modes.get(user_id) == "ingles":
        print(f"🇬🇧 [Teacher English] Consulta de texto: '{raw_text}'")
        msg = await update.message.reply_text("🇬🇧 Analizando con Teacher English...")
    else:
        print(f"📩 ¡Mensaje de texto recibido! Iniciando debate...")
        msg = await update.message.reply_text("🧠 Pensando y consultando la bóveda...")
    
    await execute_gemini_flow(msg, user_id, raw_text)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Descarga notas de voz, las transcribe y las envía al flujo conversacional."""
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

        # Comprobar si pide salir de Teacher English por voz
        if transcription.strip().lower() in ["salir", "exit", "volver", "cancelar"]:
            if user_modes.get(user_id) == "ingles":
                user_modes[user_id] = "normal"
                await msg.edit_text(
                    "👋 Has salido de <b>Teacher English</b>. De vuelta a tu Cerebro Digital.",
                    parse_mode='HTML'
                )
                await update.message.reply_text("Menú Principal:", reply_markup=get_main_keyboard())
                return
            
        prefix_html = f"🗣️ <i>Tú dijiste: {html.escape(transcription)}</i>\n\n"
        if user_modes.get(user_id) == "ingles":
            await msg.edit_text(prefix_html + "🇬🇧 Analizando pronunciación y significado...", parse_mode='HTML')
        else:
            await msg.edit_text(prefix_html + "🧠 Pensando mi respuesta y consultando la bóveda...", parse_mode='HTML')
        
        await execute_gemini_flow(msg, user_id, transcription, prefix_html)
            
    except Exception as e:
        print(f"❌ [Error] Excepción en handle_voice: {e}")
        log_error(user_id)
        await msg.edit_text("❌ Error inesperado procesando la nota.")
