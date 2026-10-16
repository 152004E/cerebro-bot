import html
import re
import time
from typing import Optional, List
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from core.telemetry import MAX_DAILY_REQUESTS
from core.telegram.state import user_requests_minute, trivia_options, user_modes

def get_dynamic_keyboard(
    latency: Optional[float], 
    tokens: Optional[int], 
    response_text: str, 
    current_requests: int = 0, 
    is_traductor: bool = False, 
    is_tutor: bool = False, 
    ai_buttons: Optional[List[str]] = None, 
    user_id: Optional[int] = None
) -> Optional[InlineKeyboardMarkup]:
    """Genera el teclado dinámico con métricas en la fila 1 y botones condicionados en filas posteriores."""
    global user_requests_minute
    current_time = time.time()
    
    user_requests_minute[:] = [t for t in user_requests_minute if current_time - t < 60]
    
    keyboard = []
    
    if latency is not None and tokens is not None:
        tokens_left = 250000 - tokens
        if tokens_left < 0:
            tokens_left = 0
        metrics_text = f"⏱️ {latency:.1f}s | 🧠 {tokens_left/1000:.0f}k | ✉️ {MAX_DAILY_REQUESTS - current_requests}/{MAX_DAILY_REQUESTS}"
        keyboard.append([InlineKeyboardButton(metrics_text, callback_data='ignore')])
        
    if ai_buttons and user_id:
        trivia_options[user_id] = ai_buttons
        for i, btn_text in enumerate(ai_buttons):
            keyboard.append([InlineKeyboardButton(f"🔸 {btn_text}", callback_data=f"ai_ans_{i}")])
            
    if is_traductor or (user_id and user_modes.get(user_id) == "ingles"):
        keyboard.append([
            InlineKeyboardButton("💾 Guardar Palabra", callback_data='save_vault_traductor'),
            InlineKeyboardButton("❓ Explicar mejor", callback_data='btn_explicar_mejor')
        ])
        keyboard.append([
            InlineKeyboardButton("❌ Salir de Teacher English", callback_data='btn_salir_modo')
        ])
    elif not is_tutor and len(response_text) > 500:
        keyboard.append([InlineKeyboardButton("💾 Guardar Idea en Obsidian", callback_data='save_vault')])
        
    if not keyboard:
        return None
        
    return InlineKeyboardMarkup(keyboard)

def get_main_keyboard() -> InlineKeyboardMarkup:
    """Retorna el teclado principal del menú."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Proyectos", callback_data='btn_proyectos'),
         InlineKeyboardButton("📥 Pendientes", callback_data='btn_pendientes')],
        [InlineKeyboardButton("🇬🇧 Teacher English", callback_data='btn_ingles'),
         InlineKeyboardButton("➕ Más opciones", callback_data='btn_mas_opciones')]
    ])

def get_more_options_keyboard() -> InlineKeyboardMarkup:
    """Retorna el teclado secundario con opciones avanzadas."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Sugerir Tarea", callback_data='btn_sugerir_tarea')],
        [InlineKeyboardButton("🧹 Auditoría", callback_data='btn_auditoria')],
        [InlineKeyboardButton("🎲 Examen Aleatorio", callback_data='btn_examen_menu')],
        [InlineKeyboardButton("🔙 Volver al Inicio", callback_data='btn_volver_main')]
    ])

def get_exam_keyboard() -> InlineKeyboardMarkup:
    """Retorna el menú de selección de exámenes técnicos y de idiomas."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💻 Desarrollo", callback_data='btn_examen_dev')],
        [InlineKeyboardButton("🇬🇧 Examen Inglés", callback_data='btn_examen_ingles')],
        [InlineKeyboardButton("🔙 Volver Atrás", callback_data='btn_mas_opciones')]
    ])

def format_for_telegram_html(text: str) -> str:
    """Convierte Markdown estándar al HTML seguro y limpio de Telegram."""
    text = html.escape(text)
    text = re.sub(r'^\s*\*\s+', '• ', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*-\s+', '• ', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    return text
