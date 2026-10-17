import html
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
import telegram.error
from telegram.ext import ContextTypes

from core.telegram.state import trivia_options, user_modes, last_user_prompts
from core.telegram.ui import get_main_keyboard, get_more_options_keyboard, get_exam_keyboard
from core.telegram.handlers import execute_gemini_flow
from core.ai import generate_final_markdown
from core.github import upload_to_obsidian
from core.telemetry import log_success, log_error

async def handle_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enrutador central para todos los botones interactivos (InlineKeyboard)."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    if query.data == 'ignore':
        return
        
    if query.data.startswith('ai_ans_'):
        idx_str = query.data.replace('ai_ans_', '')
        user_opts = trivia_options.get(user_id, [])
        
        if idx_str.isdigit():
            idx = int(idx_str)
            answer = user_opts[idx] if idx < len(user_opts) else f"Opción {idx+1}"
        else:
            answer = idx_str # Compatibilidad con botones anteriores
            
        msg = await query.message.reply_text(f"🗣️ Elegiste: <b>{html.escape(answer)}</b>\n🧠 Evaluando...", parse_mode='HTML')
        
        prompt = (
            f"[SISTEMA] El usuario seleccionó la opción: '{answer}'. Actúa como máquina de Trivia. "
            "Tu respuesta debe ir DIRECTO AL GRANO con esta estructura EXACTA:\n\n"
            "[Dime si acertó o falló MUY brevemente, ej: '✅ ¡Correcto!' o '❌ Fallaste, era X'].\n\n"
            "Pregunta: [Formula una NUEVA pregunta precisa de mi vocabulario ('Idiomas/Ingles')].\n"
            "NOTA: Si mi Vocabulario tiene muy pocas palabras para hacer preguntas variadas, INVENTA TÚ MISMO una pregunta sobre una palabra nueva en inglés (nivel intermedio) que no esté en mi vocabulario para que yo la aprenda.\n\n"
            "REGLAS:\n"
            "1. NO hables de tu proceso de lectura ni incluyas introducciones.\n"
            "2. Dame 3 nuevas opciones obligatoriamente usando el formato: [BOTON: Opcion].\n"
            "3. Termina el mensaje con la etiqueta secreta: [MODO_TUTOR]"
        )
        await execute_gemini_flow(msg, user_id, prompt)
        return
        
    # Navegación de menús
    if query.data == 'btn_mas_opciones':
        await query.message.edit_reply_markup(reply_markup=get_more_options_keyboard())
        return
    if query.data == 'btn_volver_main':
        await query.message.edit_reply_markup(reply_markup=get_main_keyboard())
        return
    if query.data == 'btn_examen_menu':
        await query.message.edit_reply_markup(reply_markup=get_exam_keyboard())
        return

    # Fase 1: Inteligencia RAG para Pendientes y Proyectos
    if query.data == 'btn_pendientes':
        prompt = (
            "Revisa la carpeta '03-Bandeja_de_Entrada' en mi bóveda. "
            "Hazme una lista de las notas que tengo pendientes (ignora Indice_Bandeja_Entrada). "
            "Para cada nota, dame el título y un resumen muy breve de máximo 2 líneas de lo que trata."
        )
        msg = await query.message.reply_text("🧠 Analizando tus notas pendientes...")
        await execute_gemini_flow(msg, user_id, prompt)
        return

    if query.data == 'btn_proyectos':
        prompt = (
            "Revisa mi bóveda y hazme una lista de mis proyectos activos (en '01-Proyectos'). "
            "Para cada uno, dame solo el nombre y una descripción de máximo 1 línea."
        )
        msg = await query.message.reply_text("🧠 Analizando proyectos activos en la bóveda...")
        await execute_gemini_flow(msg, user_id, prompt)
        return

    # Fase 3: Modo Teacher English
    if query.data == 'btn_ingles':
        user_modes[user_id] = "ingles"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Salir de Teacher English", callback_data='btn_salir_modo')]
        ])
        await query.message.reply_text(
            "🇬🇧 <b>Teacher English Activo</b>\n\n"
            "Envíame una palabra o frase en inglés (por texto o nota de voz) para analizarla, traducirla y explicar su pronunciación.\n\n"
            "<i>Para salir de este modo en cualquier momento, presiona el botón abajo o escribe /salir.</i>",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return

    if query.data == 'btn_salir_modo':
        user_modes[user_id] = "normal"
        await query.message.reply_text(
            "👋 Has salido de <b>Teacher English</b>. De vuelta a tu Cerebro Digital.",
            reply_markup=get_main_keyboard(),
            parse_mode='HTML'
        )
        return
        
    if query.data == 'btn_explicar_mejor':
        prompt = "Explícame la palabra anterior de forma más detallada, con un ejemplo más sencillo y dame consejos para pronunciarla mejor. No olvides incluir el tag [MODO_TRADUCTOR] al final."
        msg = await query.message.reply_text("🧠 Pensando una explicación más sencilla...")
        await execute_gemini_flow(msg, user_id, prompt)
        return

    if query.data == 'cancel_save_traductor':
        user_modes[user_id] = "ingles"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Salir de Teacher English", callback_data='btn_salir_modo')]
        ])
        await query.message.reply_text(
            "👍 <b>Operación cancelada.</b> Se mantiene la definición existente en tu vocabulario.\n\n🇬🇧 <i>Envíame otra palabra cuando gustes.</i>",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return

    if query.data in ['save_vault_traductor', 'confirm_save_traductor']:
        is_override = (query.data == 'confirm_save_traductor')
        original_card = query.message.text_html if hasattr(query.message, 'text_html') and query.message.text_html else html.escape(query.message.text)
        
        last_word = last_user_prompts.get(user_id, "").strip()
        
        from core.srs import find_word_in_categories, get_category_target_file, get_all_cards
        
        # 1. Comprobación antiduplicados previa
        if not is_override and last_word:
            existing = find_word_in_categories(last_word)
            if existing:
                card, cat_file = existing
                dupe_warning = (
                    f"⚠️ <b>¡Atención! La palabra \"{html.escape(card.word)}\" YA existe en tu vocabulario:</b>\n\n"
                    f"📁 <b>Archivo actual:</b> <code>{html.escape(cat_file)}</code>\n"
                    f"• <b>Categoría:</b> {html.escape(card.category)}\n"
                    f"• <b>Significado:</b> {html.escape(card.meaning)}\n"
                    f"• <b>Ejemplo:</b> <i>\"{html.escape(card.example)}\"</i>\n\n"
                    f"¿Deseas reemplazarla con la nueva explicación o cancelar para no duplicar?"
                )
                keyboard_dupe = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Reemplazar / Actualizar", callback_data='confirm_save_traductor')],
                    [InlineKeyboardButton("❌ Cancelar (Mantener actual)", callback_data='cancel_save_traductor')]
                ])
                await query.message.reply_text(dupe_warning, reply_markup=keyboard_dupe, parse_mode='HTML')
                return

        # 2. Detectar categoría del mensaje para enrutamiento limpio
        raw_msg = query.message.text or ""
        cat_match = re.search(r'Categoría:\s*([^\n]+)', raw_msg, re.IGNORECASE)
        cat_raw = cat_match.group(1).strip() if cat_match else "General"
        target_file_rel, cat_filename = get_category_target_file(cat_raw, last_word)
        
        try:
            await query.edit_message_text(
                text=f"{original_card}\n\n⏳ <i>Guardando en Categorias/{cat_filename}...</i>",
                parse_mode='HTML'
            )
        except Exception:
            pass

        result = generate_final_markdown(user_id, is_traductor=True, target_file_override=target_file_rel)
        if not result:
            log_error(user_id)
            await query.edit_message_text(
                text=f"{original_card}\n\n❌ No se pudo guardar la palabra o la sesión expiró.",
                parse_mode='HTML'
            )
            return
            
        log_success(user_id, result["tokens"], result["latency"])
        markdown_text = result["text"]
        file_path = upload_to_obsidian(markdown_text)
        
        # Forzar actualización inmediata del diccionario SRS
        try:
            get_all_cards(force_reload=True)
        except Exception:
            pass
        
        user_modes[user_id] = "ingles"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Salir de Teacher English", callback_data='btn_salir_modo')]
        ])
        
        if file_path:
            final_text = (
                f"{original_card}\n\n"
                f"────────────────────────\n"
                f"✅ <b>Guardada exitosamente en:</b>\n<code>{html.escape(file_path)}</code>\n\n"
                f"🇬🇧 <i>Sigo en Teacher English. Envíame la siguiente palabra o frase cuando gustes.</i>"
            )
            try:
                await query.edit_message_text(
                    text=final_text, 
                    reply_markup=keyboard, 
                    parse_mode='HTML'
                )
            except telegram.error.BadRequest:
                await query.edit_message_text(
                    text=f"{query.message.text}\n\n✅ Guardada en: {file_path}\n\n🇬🇧 Sigo en Teacher English.",
                    reply_markup=keyboard
                )
        else:
            await query.edit_message_text(
                text=f"{original_card}\n\n❌ Falló el append en GitHub.", 
                reply_markup=keyboard,
                parse_mode='HTML'
            )
        return

    # Fase 4: Exámenes Aleatorios
    if query.data == 'btn_examen_dev':
        prompt = (
            "Saca un concepto complejo al azar EXCLUSIVAMENTE de mis carpetas 'DevOps_y_Sistemas' o 'Desarrollo_y_Software'. "
            "Quiero que actúes como un entrevistador técnico. Hazme 1 sola pregunta difícil sobre ese concepto sin darme la respuesta, "
            "y espera a que te conteste para evaluarme."
        )
        msg = await query.message.reply_text("🧠 Preparando entrevista técnica...")
        await execute_gemini_flow(msg, user_id, prompt)
        return

    if query.data == 'btn_examen_ingles':
        prompt = (
            "ESTA ES UNA INSTRUCCIÓN DE SISTEMA: Eres un JUEGO DE TRIVIA DE INGLÉS AMERICANO estricto y rápido. "
            "Lee mi Vocabulario guardado en 'Idiomas/Ingles' en absoluto silencio (NUNCA menciones qué palabras leíste o qué estás haciendo). "
            "Tu respuesta debe ir DIRECTO AL GRANO y tener EXACTAMENTE esta estructura:\n\n"
            "🎲 ¡Trivia Time!\n\n"
            "Pregunta: [Formula la pregunta con términos gramaticales precisos. Ej: '¿Cuál es el pasado simple del verbo X?', '¿Cuál es el pasado perfecto de Y?', o 'Completa la oración']. "
            "NOTA: Si mi Vocabulario tiene muy pocas palabras para hacer preguntas variadas, INVENTA TÚ MISMO una pregunta sobre una palabra nueva en inglés (nivel intermedio) que no esté en mi vocabulario para enseñármela.\n\n"
            "REGLAS:\n"
            "1. CERO introducciones o saludos. Nada de '¡Entendido!'. Empieza directamente con '🎲 ¡Trivia Time!'.\n"
            "2. Inventa 3 opciones de respuesta.\n"
            "3. Para CADA opción, usa este formato estricto al final del mensaje: [BOTON: Opcion].\n"
            "4. Agrega la etiqueta secreta al final: [MODO_TUTOR]."
        )
        msg = await query.message.reply_text("🎲 ¡Iniciando Trivia de Inglés!")
        await execute_gemini_flow(msg, user_id, prompt)
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
        return

    # ==========================================================
    # 5. SISTEMA SRS Y MINIJUEGOS DE INGLÉS (DUOLINGO CON PODERES)
    # ==========================================================
    from core.telegram.state import user_srs_session
    from core.telegram.ui import (
        get_srs_hub_keyboard, get_srs_choice_keyboard,
        get_srs_flashcard_keyboard, get_srs_hint_keyboard,
        get_srs_feedback_keyboard
    )
    from core.srs import (
        get_due_cards, get_card_by_slug, record_answer,
        get_user_srs_summary, build_trivia_question,
        build_writing_challenge, build_flashcard, format_teacher_card
    )

    if query.data in ['btn_srs_hub', 'btn_examen_ingles']:
        summary = get_user_srs_summary(user_id)
        texto = (
            "🇬🇧 <b>Entrenador de Inglés Inteligente (SRS)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🏆 <b>Nivel:</b> {summary['level']} | ⭐ <b>XP:</b> {summary['total_xp']}\n"
            f"🔥 <b>Racha:</b> {summary['streak']} días | 📖 <b>Dominadas:</b> {summary['mastered']}/{summary['total_cards']}\n\n"
            "Elige tu modo de práctica:"
        )
        await query.message.reply_text(texto, reply_markup=get_srs_hub_keyboard(), parse_mode='HTML')
        return

    if query.data == 'btn_srs_stats':
        s = get_user_srs_summary(user_id)
        texto = (
            "📊 <b>Tus Estadísticas de Inglés</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⭐ <b>Total XP:</b> {s['total_xp']} (Nivel {s['level']})\n"
            f"🔥 <b>Racha Actual:</b> {s['streak']} días consecutivos\n"
            f"📚 <b>Vocabulario Total:</b> {s['total_cards']} palabras\n"
            f"🟢 <b>Dominadas (Caja 5):</b> {s['mastered']}\n"
            f"🟡 <b>En Aprendizaje (Cajas 1-4):</b> {s['learning']}\n"
            f"⚪ <b>Nuevas por Repasar:</b> {s['new']}\n"
            f"🔄 <b>Total Repasos Realizados:</b> {s['total_reviews']}"
        )
        await query.message.reply_text(texto, reply_markup=get_srs_hub_keyboard(), parse_mode='HTML')
        return

    if query.data == 'btn_srs_start_trivia':
        due = get_due_cards(user_id, count=6)
        user_srs_session[user_id] = {
            "mode": "trivia",
            "queue": due,
            "index": 0,
            "current_card": due[0] if due else None
        }
        if not due:
            await query.message.reply_text("✅ ¡No tienes palabras pendientes por hoy! Excelente trabajo.", reply_markup=get_srs_hub_keyboard())
            return
            
        q = build_trivia_question(due[0])
        user_srs_session[user_id]["current_game"] = q
        await query.message.reply_text(
            q["text"], 
            reply_markup=get_srs_choice_keyboard(q["options"], due[0].slug),
            parse_mode='HTML'
        )
        return

    if query.data == 'btn_srs_start_writing':
        due = get_due_cards(user_id, count=6)
        if not due:
            await query.message.reply_text("✅ ¡Vocabulario al día!", reply_markup=get_srs_hub_keyboard())
            return
            
        user_srs_session[user_id] = {
            "mode": "writing",
            "queue": due,
            "index": 0,
            "current_card": due[0],
            "waiting_input": True
        }
        w = build_writing_challenge(due[0])
        user_srs_session[user_id]["current_game"] = w
        await query.message.reply_text(w["text"], parse_mode='HTML')
        return

    if query.data == 'btn_srs_start_flashcards':
        due = get_due_cards(user_id, count=6)
        if not due:
            await query.message.reply_text("✅ ¡Vocabulario al día!", reply_markup=get_srs_hub_keyboard())
            return
            
        user_srs_session[user_id] = {
            "mode": "flashcard",
            "queue": due,
            "index": 0,
            "current_card": due[0]
        }
        fc = build_flashcard(due[0])
        user_srs_session[user_id]["current_game"] = fc
        await query.message.reply_text(
            fc["text"], 
            reply_markup=get_srs_flashcard_keyboard(due[0].slug),
            parse_mode='HTML'
        )
        return

    if query.data.startswith('srs_ans_'):
        idx = int(query.data.replace('srs_ans_', ''))
        sess = user_srs_session.get(user_id)
        if not sess or "current_game" not in sess:
            await query.message.reply_text("⚠️ Sesión expirada. Inicia una nueva con /study.")
            return
            
        q = sess["current_game"]
        card = sess["current_card"]
        is_correct = (idx == q["correct_idx"])
        chosen_opt = q["options"][idx] if idx < len(q["options"]) else ""
        
        if is_correct:
            xp, box, interval = record_answer(user_id, card.slug, "good")
            feedback = (
                f"🎉 <b>¡CORRECTO! (+{xp} XP)</b> ⭐\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Elegiste: <b>{chosen_opt}</b> ✅\n"
                f"Palabra: <b>{card.word}</b> <code>{card.pronunciation}</code>\n"
                f"📖 {card.meaning}\n\n"
                f"📦 <i>Avanza a Caja Leitner {box} (Próximo repaso en {interval} días)</i>"
            )
        else:
            correct_opt = q["options"][q["correct_idx"]]
            xp, box, interval = record_answer(user_id, card.slug, "again")
            feedback = (
                f"❌ <b>Fallaste:</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Elegiste: <i>{chosen_opt}</i>\n"
                f"La opción correcta era: <b>{correct_opt}</b>\n"
                f"Palabra: <b>{card.word}</b> <code>{card.pronunciation}</code>\n"
                f"💡 Ejemplo: <i>\"{card.example}\"</i>\n\n"
                f"📦 <i>Vuelve a Caja 1 para afianzar (+{xp} XP)</i>"
            )
            
        await query.message.reply_text(feedback, reply_markup=get_srs_feedback_keyboard(), parse_mode='HTML')
        return

    if query.data.startswith('srs_hint_'):
        slug = query.data.replace('srs_hint_', '').strip()
        card = get_card_by_slug(slug)
        if card:
            teacher_text = format_teacher_card(card)
            await query.message.reply_text(teacher_text, reply_markup=get_srs_hint_keyboard(), parse_mode='HTML')
        else:
            await query.message.reply_text("⚠️ No se encontró la ficha.", reply_markup=get_srs_hint_keyboard())
        return

    if query.data.startswith('srs_rate_'):
        quality = query.data.replace('srs_rate_', '')
        sess = user_srs_session.get(user_id)
        if sess and "current_card" in sess:
            card = sess["current_card"]
            xp, box, interval = record_answer(user_id, card.slug, quality)
            # Avanzar automáticamente al siguiente
            sess["index"] += 1
            idx = sess["index"]
            queue = sess.get("queue", [])
            if idx < len(queue):
                next_card = queue[idx]
                sess["current_card"] = next_card
                fc = build_flashcard(next_card)
                sess["current_game"] = fc
                await query.message.reply_text(
                    f"⭐ <b>+{xp} XP</b> · Programada a Caja {box} ({interval}d)\n\n" + fc["text"],
                    reply_markup=get_srs_flashcard_keyboard(next_card.slug),
                    parse_mode='HTML'
                )
            else:
                await query.message.reply_text(
                    f"🎉 <b>¡Sesión de Flashcards Completada! (+{xp} XP)</b>\n"
                    "Todas las tarjetas de la tanda han sido repasadas.",
                    reply_markup=get_srs_hub_keyboard(),
                    parse_mode='HTML'
                )
        return

    if query.data == 'srs_next':
        sess = user_srs_session.get(user_id)
        if not sess or "queue" not in sess:
            await query.message.reply_text("Sesión finalizada. Usa /study para repasar.", reply_markup=get_srs_hub_keyboard())
            return
            
        sess["index"] += 1
        idx = sess["index"]
        queue = sess.get("queue", [])
        
        if idx >= len(queue):
            summary = get_user_srs_summary(user_id)
            await query.message.reply_text(
                f"🎉 <b>¡Misión de Repaso Cumplida!</b> 🚀\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Has completado la tanda de hoy.\n"
                f"⭐ <b>Total XP acumulado:</b> {summary['total_xp']}\n"
                f"🔥 <b>Racha:</b> {summary['streak']} días consecutivos.\n\n"
                f"¡Buen trabajo!",
                reply_markup=get_srs_hub_keyboard(),
                parse_mode='HTML'
            )
            return
            
        next_card = queue[idx]
        sess["current_card"] = next_card
        mode = sess.get("mode", "trivia")
        
        if mode == "trivia":
            q = build_trivia_question(next_card)
            sess["current_game"] = q
            await query.message.reply_text(
                q["text"],
                reply_markup=get_srs_choice_keyboard(q["options"], next_card.slug),
                parse_mode='HTML'
            )
        elif mode == "writing":
            sess["waiting_input"] = True
            w = build_writing_challenge(next_card)
            sess["current_game"] = w
            await query.message.reply_text(w["text"], parse_mode='HTML')
        elif mode == "flashcard":
            fc = build_flashcard(next_card)
            sess["current_game"] = fc
            await query.message.reply_text(
                fc["text"],
                reply_markup=get_srs_flashcard_keyboard(next_card.slug),
                parse_mode='HTML'
            )
        return

