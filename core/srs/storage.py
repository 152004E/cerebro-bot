import os
import json
import threading
from typing import Dict, Tuple, Optional
from datetime import datetime

from core.srs.models import CardProgress, UserStats

REL_SRS_PATH = "02-Conocimiento/Idiomas/Ingles/srs_state.json"

def get_vault_srs_path() -> str:
    """Obtiene la ruta local hacia srs_state.json en la bóveda o directorio local."""
    default_vault = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../cerebro"))
    if os.path.exists(default_vault):
        target_dir = os.path.join(default_vault, "02-Conocimiento/Idiomas/Ingles")
        os.makedirs(target_dir, exist_ok=True)
        return os.path.join(target_dir, "srs_state.json")
        
    tmp_vault = "/tmp/cerebro_vault"
    if os.path.exists(tmp_vault):
        target_dir = os.path.join(tmp_vault, "02-Conocimiento/Idiomas/Ingles")
        os.makedirs(target_dir, exist_ok=True)
        return os.path.join(target_dir, "srs_state.json")
        
    # Fallback local en core
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "srs_state.json"))

def load_srs_state(user_id: int) -> Tuple[UserStats, Dict[str, CardProgress]]:
    """Carga las estadísticas del usuario y el progreso de cada tarjeta."""
    path = get_vault_srs_path()
    
    # Intentar cargar desde archivo local
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            user_data = data.get(str(user_id), {})
            stats_raw = user_data.get("stats", {})
            stats = UserStats(
                total_xp=stats_raw.get("total_xp", 0),
                current_streak=stats_raw.get("current_streak", 0),
                last_study_date=stats_raw.get("last_study_date"),
                cards_mastered=stats_raw.get("cards_mastered", 0),
                total_reviews=stats_raw.get("total_reviews", 0)
            )
            
            cards: Dict[str, CardProgress] = {}
            for slug, c_raw in user_data.get("cards", {}).items():
                cards[slug] = CardProgress(
                    box=c_raw.get("box", 1),
                    interval_days=c_raw.get("interval_days", 1),
                    last_reviewed=c_raw.get("last_reviewed"),
                    next_review=c_raw.get("next_review", datetime.now().isoformat()),
                    consecutive_correct=c_raw.get("consecutive_correct", 0),
                    lapses=c_raw.get("lapses", 0)
                )
            return stats, cards
        except Exception as e:
            print(f"⚠️ Error leyendo {path}: {e}")
            
    # Intentar cargar desde GitHub si no existe localmente
    try:
        from core.github import repo
        contents = repo.get_contents(REL_SRS_PATH, ref="main")
        data = json.loads(contents.decoded_content.decode("utf-8"))
        user_data = data.get(str(user_id), {})
        stats_raw = user_data.get("stats", {})
        stats = UserStats(
            total_xp=stats_raw.get("total_xp", 0),
            current_streak=stats_raw.get("current_streak", 0),
            last_study_date=stats_raw.get("last_study_date"),
            cards_mastered=stats_raw.get("cards_mastered", 0),
            total_reviews=stats_raw.get("total_reviews", 0)
        )
        cards: Dict[str, CardProgress] = {}
        for slug, c_raw in user_data.get("cards", {}).items():
            cards[slug] = CardProgress(
                box=c_raw.get("box", 1),
                interval_days=c_raw.get("interval_days", 1),
                last_reviewed=c_raw.get("last_reviewed"),
                next_review=c_raw.get("next_review", datetime.now().isoformat()),
                consecutive_correct=c_raw.get("consecutive_correct", 0),
                lapses=c_raw.get("lapses", 0)
            )
        # Guardar en local para cache
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return stats, cards
    except Exception:
        pass

    return UserStats(), {}

def _sync_to_github_thread(json_content: str):
    """Sincroniza en un hilo asíncrono hacia GitHub para no bloquear a Telegram."""
    try:
        from core.github import repo
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        commit_msg = f"🤖 Bot: Actualizar progreso SRS ({timestamp})"
        try:
            contents = repo.get_contents(REL_SRS_PATH, ref="main")
            repo.update_file(contents.path, commit_msg, json_content, contents.sha, branch="main")
            print("☁️ [GitHub SRS] Progreso sincronizado con GitHub exitosamente.")
        except Exception:
            repo.create_file(path=REL_SRS_PATH, message=commit_msg, content=json_content, branch="main")
            print("☁️ [GitHub SRS] Archivo srs_state.json creado en GitHub.")
    except Exception as e:
        print(f"⚠️ [GitHub SRS Error] {e}")

def save_srs_state(user_id: int, stats: UserStats, cards: Dict[str, CardProgress], sync_git: bool = True):
    """Guarda el estado SRS del usuario en local y opcionalmente en GitHub."""
    path = get_vault_srs_path()
    
    full_data = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                full_data = json.load(f)
        except Exception:
            full_data = {}
            
    cards_dict = {}
    for slug, c in cards.items():
        cards_dict[slug] = {
            "box": c.box,
            "interval_days": c.interval_days,
            "last_reviewed": c.last_reviewed,
            "next_review": c.next_review,
            "consecutive_correct": c.consecutive_correct,
            "lapses": c.lapses
        }
        
    full_data[str(user_id)] = {
        "stats": {
            "total_xp": stats.total_xp,
            "current_streak": stats.current_streak,
            "last_study_date": stats.last_study_date,
            "cards_mastered": stats.cards_mastered,
            "total_reviews": stats.total_reviews
        },
        "cards": cards_dict
    }
    
    json_str = json.dumps(full_data, indent=2, ensure_ascii=False)
    
    # 1. Guardar local
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(json_str)
    except Exception as e:
        print(f"⚠️ Error guardando local SRS en {path}: {e}")
        
    # 2. Sincronizar con GitHub en segundo plano
    if sync_git:
        threading.Thread(target=_sync_to_github_thread, args=(json_str,), daemon=True).start()
