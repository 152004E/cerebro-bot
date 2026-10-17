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
        [InlineKeyboardButton("🇬🇧 Entrenador SRS (Duolingo)", callback_data='btn_srs_hub')],
        [InlineKeyboardButton("🔙 Volver Atrás", callback_data='btn_mas_opciones')]
    ])

def get_srs_hub_keyboard() -> InlineKeyboardMarkup:
    """Retorna el menú principal del Entrenador de Inglés con Repetición Espaciada."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Trivia de Opciones (SRS)", callback_data='btn_srs_start_trivia')],
        [InlineKeyboardButton("✍️ Reto de Escritura", callback_data='btn_srs_start_writing')],
        [InlineKeyboardButton("🎴 Flashcards Inteligentes", callback_data='btn_srs_start_flashcards')],
        [InlineKeyboardButton("📊 Mi Progreso (XP y Racha)", callback_data='btn_srs_stats')],
        [InlineKeyboardButton("🔙 Volver al Menú Principal", callback_data='btn_volver_main')]
    ])

def get_srs_choice_keyboard(options: List[str], slug: str) -> InlineKeyboardMarkup:
    """Genera botones para las 4 opciones de trivia y botón de pista."""
    keyboard = []
    letters = ["A", "B", "C", "D"]
    for i, opt in enumerate(options):
        prefix = letters[i] if i < len(letters) else str(i+1)
        keyboard.append([InlineKeyboardButton(f"{prefix}) {opt}", callback_data=f"srs_ans_{i}")])
        
    keyboard.append([
        InlineKeyboardButton("💡 Ver Pista Completa", callback_data=f"srs_hint_{slug}")
    ])
    keyboard.append([
        InlineKeyboardButton("⏹️ Salir de la Sesión", callback_data='btn_srs_hub')
    ])
    return InlineKeyboardMarkup(keyboard)

def get_srs_flashcard_keyboard(slug: str) -> InlineKeyboardMarkup:
    """Botones de autoevaluación Leitner para Flashcards."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔴 Otra vez", callback_data="srs_rate_again"),
         InlineKeyboardButton("🟡 Difícil", callback_data="srs_rate_hard")],
        [InlineKeyboardButton("🟢 Bien", callback_data="srs_rate_good"),
         InlineKeyboardButton("🚀 Fácil", callback_data="srs_rate_easy")],
        [InlineKeyboardButton("💡 Ficha Teacher", callback_data=f"srs_hint_{slug}"),
         InlineKeyboardButton("⏹️ Salir", callback_data="btn_srs_hub")]
    ])

def get_srs_hint_keyboard() -> InlineKeyboardMarkup:
    """Botón tras consultar una pista de Teacher English."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🆗 Entendido, Siguiente ➡️", callback_data='srs_next')]
    ])

def get_srs_feedback_keyboard() -> InlineKeyboardMarkup:
    """Botón tras responder para avanzar a la siguiente pregunta."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➡️ Siguiente Pregunta", callback_data='srs_next'),
         InlineKeyboardButton("⏹️ Salir", callback_data='btn_srs_hub')]
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
