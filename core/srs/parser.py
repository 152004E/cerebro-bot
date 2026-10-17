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

def get_vocabulario_path(vault_base_path: Optional[str] = None) -> Optional[str]:
    """Retorna la ruta absoluta del archivo Vocabulario.md disponible."""
    paths_to_check = []
    if vault_base_path:
        paths_to_check.append(os.path.join(vault_base_path, "02-Conocimiento/Idiomas/Ingles/Vocabulario.md"))
        
    default_vault = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../cerebro"))
    paths_to_check.append(os.path.join(default_vault, "02-Conocimiento/Idiomas/Ingles/Vocabulario.md"))
    paths_to_check.append("/tmp/cerebro_vault/02-Conocimiento/Idiomas/Ingles/Vocabulario.md")
    
    for path in paths_to_check:
        if os.path.exists(path):
            return path
    return None

def get_categorias_dir(vault_base_path: Optional[str] = None) -> Optional[str]:
    """Retorna la ruta absoluta del directorio Categorias disponible."""
    paths_to_check = []
    if vault_base_path:
        paths_to_check.append(os.path.join(vault_base_path, "02-Conocimiento/Idiomas/Ingles/Categorias"))
        
    default_vault = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../cerebro"))
    paths_to_check.append(os.path.join(default_vault, "02-Conocimiento/Idiomas/Ingles/Categorias"))
    paths_to_check.append("/tmp/cerebro_vault/02-Conocimiento/Idiomas/Ingles/Categorias")
    
    for path in paths_to_check:
        if os.path.exists(path) and os.path.isdir(path):
            return path
    return None

def get_category_target_file(category_raw: str, word: str = "") -> Tuple[str, str]:
    """
    Normaliza la categoría detectada por la IA y devuelve:
    (ruta_relativa_github, nombre_archivo)
    """
    cat_lower = category_raw.lower()
    word_lower = word.lower()
    
    if "phrasal" in cat_lower or (" " in word_lower and any(w in word_lower for w in ["up", "in", "out", "on", "off", "away"])):
        filename = "Phrasal_Verbs.md"
    elif "frase" in cat_lower or "conjunción" in cat_lower or "expresión" in cat_lower:
        filename = "Expresiones_y_Frases.md"
    elif "verbo" in cat_lower:
        filename = "Verbos.md"
    elif "sustantivo" in cat_lower:
        filename = "Sustantivos.md"
    elif "adjetivo" in cat_lower:
        filename = "Adjetivos.md"
    elif "adverbio" in cat_lower:
        filename = "Adverbios.md"
    else:
        filename = "Expresiones_y_Frases.md"
        
    rel_path = f"02-Conocimiento/Idiomas/Ingles/Categorias/{filename}"
    return rel_path, filename

def load_vocabulario_from_vault(vault_base_path: Optional[str] = None) -> List[WordCard]:
    """
    Carga todas las tarjetas escaneando la subcarpeta Categorias/
    o Vocabulario.md si la carpeta no existe.
    """
    cards: List[WordCard] = []
    cat_dir = get_categorias_dir(vault_base_path)
    
    if cat_dir and os.path.exists(cat_dir):
        # Leer todos los archivos .md dentro de Categorias/
        for fname in sorted(os.listdir(cat_dir)):
            if fname.endswith(".md"):
                fpath = os.path.join(cat_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    parsed = parse_vocabulario_markdown(content)
                    cards.extend(parsed)
                except Exception as e:
                    print(f"⚠️ Error leyendo {fpath}: {e}")
                    
        if cards:
            # Deduplicar por slug
            unique: Dict[str, WordCard] = {}
            for c in cards:
                unique[c.slug] = c
            return list(unique.values())
            
    # Fallback al archivo único Vocabulario.md
    path = get_vocabulario_path(vault_base_path)
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return parse_vocabulario_markdown(content)
        except Exception as e:
            print(f"⚠️ Error leyendo Vocabulario en {path}: {e}")
                
    return []

def find_word_in_categories(word_or_slug: str, vault_base_path: Optional[str] = None) -> Optional[Tuple[WordCard, str]]:
    """
    Busca si una palabra ya existe en alguna de las categorías.
    Retorna (WordCard, nombre_archivo_categoria) o None si es nueva.
    """
    target_slug = normalize_slug(word_or_slug)
    cat_dir = get_categorias_dir(vault_base_path)
    
    if cat_dir and os.path.exists(cat_dir):
        for fname in sorted(os.listdir(cat_dir)):
            if fname.endswith(".md"):
                fpath = os.path.join(cat_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    for card in parse_vocabulario_markdown(content):
                        if card.slug == target_slug or card.word.strip().lower() == word_or_slug.strip().lower():
                            return card, f"Categorias/{fname}"
                except Exception:
                    pass
    return None


