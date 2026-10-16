import html
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
import telegram.error
from telegram.ext import ContextTypes

from core.telegram.state import trivia_options, user_modes
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

    if query.data == 'save_vault_traductor':
        original_card = query.message.text_html if hasattr(query.message, 'text_html') and query.message.text_html else html.escape(query.message.text)
        
        try:
            await query.edit_message_text(
                text=f"{original_card}\n\n⏳ <i>Guardando en tu Vocabulario de Obsidian...</i>",
                parse_mode='HTML'
            )
        except Exception:
            pass

        result = generate_final_markdown(user_id, is_traductor=True)
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
