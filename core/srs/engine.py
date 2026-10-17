import random
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

from core.srs.models import WordCard, CardProgress, UserStats
from core.srs.parser import load_vocabulario_from_vault
from core.srs.storage import load_srs_state, save_srs_state

BOX_INTERVALS = {
    1: 1,   # 1 día
    2: 3,   # 3 días
    3: 7,   # 7 días
    4: 14,  # 14 días
    5: 30   # 30 días (Dominada)
}

# Caché en memoria de tarjetas y slug lookup
_ALL_CARDS_CACHE: List[WordCard] = []
_CARDS_BY_SLUG: Dict[str, WordCard] = {}

def get_all_cards() -> List[WordCard]:
    """Retorna todas las tarjetas parseadas de Vocabulario.md."""
    global _ALL_CARDS_CACHE, _CARDS_BY_SLUG
    if not _ALL_CARDS_CACHE:
        _ALL_CARDS_CACHE = load_vocabulario_from_vault()
        _CARDS_BY_SLUG = {c.slug: c for c in _ALL_CARDS_CACHE}
    return _ALL_CARDS_CACHE

def get_card_by_slug(slug: str) -> Optional[WordCard]:
    """Busca una tarjeta por su slug para comandos rápidos /pista_<slug>."""
    global _CARDS_BY_SLUG
    if not _CARDS_BY_SLUG:
        get_all_cards()
    return _CARDS_BY_SLUG.get(slug.lower().strip())

def get_due_cards(user_id: int, count: int = 8) -> List[WordCard]:
    """
    Selecciona las tarjetas que toca repasar hoy según la curva del olvido.
    Prioriza:
    1. Tarjetas en Box 1 vencidas (las que más le cuestan)
    2. Tarjetas nuevas nunca vistas
    3. Otras tarjetas vencidas
    """
    all_cards = get_all_cards()
    if not all_cards:
        return []
        
    stats, progress_map = load_srs_state(user_id)
    now = datetime.now()
    
    due_cards: List[WordCard] = []
    new_cards: List[WordCard] = []
    
    for card in all_cards:
        prog = progress_map.get(card.slug)
        if not prog:
            new_cards.append(card)
        else:
            try:
                next_dt = datetime.fromisoformat(prog.next_review)
                if next_dt <= now:
                    due_cards.append(card)
            except Exception:
                due_cards.append(card)
                
    # Ordenar due_cards poniendo las de caja 1 primero
    due_cards.sort(key=lambda c: progress_map[c.slug].box if c.slug in progress_map else 1)
    
    selected = []
    # Mezclar tarjetas vencidas con tarjetas nuevas
    if due_cards:
        selected.extend(due_cards[:count])
        
    if len(selected) < count and new_cards:
        needed = count - len(selected)
        random.shuffle(new_cards)
        selected.extend(new_cards[:needed])
        
    if not selected:
        # Si no hay ninguna vencida ni nueva, tomar al azar para mantener la práctica activa
        shuffled = list(all_cards)
        random.shuffle(shuffled)
        selected = shuffled[:count]
        
    return selected

def record_answer(user_id: int, slug: str, quality: str) -> Tuple[int, int, int]:
    """
    Registra el resultado del usuario para una tarjeta.
    quality: 'again' (fallo/pista), 'hard', 'good' (acierto), 'easy'
    Retorna: (earned_xp, current_box, interval_days)
    """
    stats, progress_map = load_srs_state(user_id)
    prog = progress_map.get(slug, CardProgress())
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    
    # Manejo de Racha Diaria
    if stats.last_study_date:
        try:
            last_dt = datetime.strptime(stats.last_study_date, "%Y-%m-%d")
            diff_days = (now.date() - last_dt.date()).days
            if diff_days == 1:
                stats.current_streak += 1
            elif diff_days > 1:
                stats.current_streak = 1
        except Exception:
            stats.current_streak = 1
    else:
        stats.current_streak = 1
        
    stats.last_study_date = today_str
    stats.total_reviews += 1
    
    earned_xp = 0
    
    if quality in ["again", "fail"]:
        prog.box = 1
        prog.interval_days = BOX_INTERVALS[1]
        prog.consecutive_correct = 0
        prog.lapses += 1
        earned_xp = 2 # XP de consuelo por esfuerzo
    elif quality == "hard":
        prog.box = max(1, prog.box)
        prog.interval_days = 2
        earned_xp = 5
    elif quality in ["good", "correct"]:
        prog.box = min(5, prog.box + 1)
        prog.interval_days = BOX_INTERVALS[prog.box]
        prog.consecutive_correct += 1
        earned_xp = 10
    elif quality == "easy":
        prog.box = min(5, prog.box + 2)
        prog.interval_days = BOX_INTERVALS[prog.box]
        prog.consecutive_correct += 2
        earned_xp = 15
        
    # Bonus de racha
    if stats.current_streak >= 3:
        earned_xp += 2
        
    stats.total_xp += earned_xp
    
    # Contar dominadas (Box 5)
    stats.cards_mastered = sum(1 for p in progress_map.values() if p.box >= 5)
    
    next_date = now + timedelta(days=prog.interval_days)
    prog.last_reviewed = now.isoformat()
    prog.next_review = next_date.isoformat()
    
    progress_map[slug] = prog
    
    # Guardar estado
    save_srs_state(user_id, stats, progress_map)
    
    return earned_xp, prog.box, prog.interval_days

def get_user_srs_summary(user_id: int) -> dict:
    """Devuelve resumen estadístico para el comando /stats o panel."""
    stats, progress_map = load_srs_state(user_id)
    all_cards = get_all_cards()
    total_cards = len(all_cards)
    
    box_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for p in progress_map.values():
        box_counts[p.box] = box_counts.get(p.box, 0) + 1
        
    level = (stats.total_xp // 100) + 1
    
    return {
        "total_xp": stats.total_xp,
        "level": level,
        "streak": stats.current_streak,
        "total_cards": total_cards,
        "mastered": box_counts[5],
        "learning": sum(box_counts[b] for b in [1, 2, 3, 4]),
        "new": total_cards - len(progress_map),
        "total_reviews": stats.total_reviews
    }
