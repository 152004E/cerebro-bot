import os
import re
from typing import Dict, List, Optional
from core.srs.models import WordCard

def normalize_slug(word: str) -> str:
    """Genera un slug limpio y compatible con comandos de Telegram (letras, numeros, _)"""
    clean = re.sub(r'[^a-zA-Z0-9]', '_', word.lower())
    clean = re.sub(r'_+', '_', clean).strip('_')
    return clean or "word"

def parse_vocabulario_markdown(content: str) -> List[WordCard]:
    """Parsea el contenido de Vocabulario.md y extrae tarjetas WordCard estructuradas."""
    cards: List[WordCard] = []
    
    # Dividir por bloques que empiezan con ### (categoría) o bloques de palabras
    sections = re.split(r'\n(?=###|\-\s+\*\*)', content)
    
    current_category = "General"
    
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
            
        # Detectar categoría en cabecera ###
        cat_match = re.search(r'###\s*\[?(?:Categoría:\s*)?([^\]\n]+)\]?', sec, re.IGNORECASE)
        if cat_match:
            current_category = cat_match.group(1).strip()
            
        # Buscar definiciones de palabras: - **Word**: Meaning (/pronunciation/)
        word_matches = list(re.finditer(
            r'-\s+\*\*([^*]+)\*\*:\s*([^\n(]+)(?:\(([^)]+)\))?',
            sec
        ))
        
        for wm in word_matches:
            raw_word = wm.group(1).strip()
            # Limpiar posibles barras o alternativas como "Calf / Calves"
            primary_word = raw_word.split('/')[0].strip()
            raw_meaning = wm.group(2).strip().rstrip('.,;')
            raw_pronunciation = wm.group(3).strip() if wm.group(3) else ""
            
            # Si no vino entre paréntesis al lado, buscar en el bloque
            if not raw_pronunciation:
                pron_match = re.search(r'(?:/|\()([^/\n)]+)(?:/|\))', sec)
                if pron_match:
                    raw_pronunciation = f"/{pron_match.group(1).strip()}/"
            elif not raw_pronunciation.startswith('/'):
                raw_pronunciation = f"/{raw_pronunciation}/"
                
            # Extraer ejemplo
            ex_match = re.search(r'(?:-\s*Ejemplo:\s*|\*Ejemplo:\*\s*)([^\n]+)', sec, re.IGNORECASE)
            example = ex_match.group(1).strip().strip('"*') if ex_match else ""
            
            # Extraer detalles/usos
            det_match = re.search(r'(?:-\s*Detalles[^\n:]*:\s*)([^\n]+)', sec, re.IGNORECASE)
            details = det_match.group(1).strip() if det_match else ""
            
            slug = normalize_slug(primary_word)
            
            card = WordCard(
                word=primary_word,
                slug=slug,
                category=current_category,
                meaning=raw_meaning,
                pronunciation=raw_pronunciation,
                example=example,
                details=details
            )
            cards.append(card)
            
    # Eliminar duplicados priorizando la última definición más completa
    unique_cards: Dict[str, WordCard] = {}
    for c in cards:
        unique_cards[c.slug] = c
        
    return list(unique_cards.values())

def load_vocabulario_from_vault(vault_base_path: Optional[str] = None) -> List[WordCard]:
    """Carga Vocabulario.md desde la ruta local de la bóveda o /tmp/cerebro_vault."""
    paths_to_check = []
    if vault_base_path:
        paths_to_check.append(os.path.join(vault_base_path, "02-Conocimiento/Idiomas/Ingles/Vocabulario.md"))
        
    # Rutas por defecto del ecosistema Cerebro
    default_vault = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../cerebro"))
    paths_to_check.append(os.path.join(default_vault, "02-Conocimiento/Idiomas/Ingles/Vocabulario.md"))
    paths_to_check.append("/tmp/cerebro_vault/02-Conocimiento/Idiomas/Ingles/Vocabulario.md")
    
    for path in paths_to_check:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                cards = parse_vocabulario_markdown(content)
                if cards:
                    return cards
            except Exception as e:
                print(f"⚠️ Error leyendo Vocabulario en {path}: {e}")
                
    return []
