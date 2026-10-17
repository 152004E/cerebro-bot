import random
import re
from typing import Dict, List, Optional, Tuple, Any

from core.srs.models import WordCard
from core.srs.engine import get_all_cards, get_card_by_slug

def format_teacher_card(card: WordCard) -> str:
    """Genera la ficha completa idéntica a Teacher English."""
    lines = [
        f"🇬🇧 <b>Ficha Teacher English · {card.word}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"• <b>Categoría:</b> {card.category}",
        f"• <b>Significado:</b> {card.meaning}",
    ]
    if card.pronunciation:
        lines.append(f"• <b>Pronunciación:</b> <code>{card.pronunciation}</code>")
    if card.example:
        lines.append(f"• <b>Ejemplo:</b> <i>\"{card.example}\"</i>")
    if card.details:
        lines.append(f"• <b>Detalles:</b> {card.details}")
        
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def build_trivia_question(card: WordCard) -> Dict[str, Any]:
    """
    Genera un reto de 4 opciones (1 correcta y 3 distractores del mismo vocabulario)
    con el comando azul /pista_<slug> integrado.
    """
    all_cards = get_all_cards()
    other_cards = [c for c in all_cards if c.slug != card.slug and c.meaning]
    
    # Seleccionar 3 distractores
    distractors = random.sample(other_cards, min(3, len(other_cards)))
    options = [card.meaning] + [d.meaning for d in distractors]
    random.shuffle(options)
    
    correct_idx = options.index(card.meaning)
    
    text = (
        f"🎲 <b>Trivia de Inglés · Modo Reto</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"¿Qué significa la palabra <b>{card.word}</b>?\n\n"
        f"👉 /pista_{card.slug} <i>(Toca el comando azul si no la recuerdas)</i>\n"
    )
    
    return {
        "type": "choice",
        "card": card,
        "text": text,
        "options": options,
        "correct_idx": correct_idx
    }

def build_writing_challenge(card: WordCard) -> Dict[str, Any]:
    """
    Genera un reto de escritura: le da el significado en español y el usuario
    debe escribir la palabra en inglés en el chat.
    """
    # Primera letra como pista sutil
    hint_letter = card.word[0].upper()
    hint_length = len(card.word)
    
    text = (
        f"✍️ <b>Reto de Escritura · Vocabulario</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"¿Cómo se dice en inglés:\n"
        f"👉 <b>\"{card.meaning}\"</b>?\n\n"
        f"💡 <i>Pista de letras: Empieza con '{hint_letter}' ({hint_length} letras)</i>\n"
        f"👉 /pista_{card.slug} <i>(Toca para ver la ficha completa)</i>\n\n"
        f"✏️ <b>Escribe la palabra en inglés directamente en el chat:</b>"
    )
    
    return {
        "type": "writing",
        "card": card,
        "text": text,
        "expected_word": card.word.strip().lower()
    }

def build_flashcard(card: WordCard) -> Dict[str, Any]:
    """Genera una Flashcard inteligente con spoiler táctil de Telegram."""
    text = (
        f"🎴 <b>Flashcard Inteligente</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Palabra: <b>{card.word}</b> {card.pronunciation}\n"
        f"Categoría: <i>{card.category}</i>\n\n"
        f"Toca para revelar el significado:\n"
        f"<tg-spoiler>📖 {card.meaning}\nEj: \"{card.example}\"</tg-spoiler>\n\n"
        f"👉 /pista_{card.slug} <i>(Ficha completa)</i>\n\n"
        f"¿Qué tan bien la recordaste?"
    )
    return {
        "type": "flashcard",
        "card": card,
        "text": text
    }

def evaluate_writing_answer(expected: str, user_text: str) -> Tuple[bool, str]:
    """Evalúa la respuesta escrita del usuario con tolerancia a mayúsculas/espacios."""
    clean_user = user_text.strip().lower()
    clean_expected = expected.strip().lower()
    
    # Coincidencia exacta
    if clean_user == clean_expected:
        return True, "exact"
        
    # Tolerancia si es verbo regular ("improve" vs "improved") o phrasal verb
    if clean_expected in clean_user or clean_user in clean_expected:
        return True, "close"
        
    return False, "wrong"
