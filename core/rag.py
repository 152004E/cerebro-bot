import os
import glob
import json
import hashlib
import numpy as np
from google import genai
import time

EMBEDDING_MODEL = 'gemini-embedding-2'
CACHE_FILE = os.path.join(os.path.dirname(__file__), 'vault_embeddings.json')

def get_file_hash(content: str) -> str:
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def sync_vault_embeddings(client: genai.Client, vault_path: str):
    print("🔄 Sincronizando Embeddings de la bóveda...")
    
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except Exception:
            cache = {}
    else:
        cache = {}

    search_paths = [
        os.path.join(vault_path, "02-Conocimiento", "**", "*.md"),
        os.path.join(vault_path, "01-Proyectos", "**", "*.md"),
        os.path.join(vault_path, "03-Bandeja_de_Entrada", "**", "*.md")
    ]
    
    current_files = {}
    needs_update = False
    
    for path in search_paths:
        for file_path in glob.glob(path, recursive=True):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if not content:
                    continue
                    
                file_hash = get_file_hash(content)
                rel_path = os.path.relpath(file_path, vault_path)
                
                if rel_path in cache and cache[rel_path]['hash'] == file_hash:
                    current_files[rel_path] = cache[rel_path]
                else:
                    print(f"Generando embedding para: {rel_path}")
                    clean_content = content[:15000] 
                    
                    # Llamada a la API
                    try:
                        response = client.models.embed_content(
                            model=EMBEDDING_MODEL,
                            contents=clean_content,
                        )
                        embedding = response.embeddings[0].values
                        
                        current_files[rel_path] = {
                            'hash': file_hash,
                            'content': clean_content,
                            'embedding': embedding
                        }
                        needs_update = True
                        time.sleep(1) # Pequeña pausa
                    except Exception as e:
                        if '429' in str(e):
                            print(f"⏳ Límite de Google alcanzado (15 por minuto). Esperando 60 segundos para continuar...")
                            time.sleep(60)
                            try:
                                response = client.models.embed_content(
                                    model=EMBEDDING_MODEL,
                                    contents=clean_content,
                                )
                                embedding = response.embeddings[0].values
                                current_files[rel_path] = {
                                    'hash': file_hash,
                                    'content': clean_content,
                                    'embedding': embedding
                                }
                                needs_update = True
                            except Exception as retry_e:
                                print(f"Error en reintento para {rel_path}: {retry_e}")
                        else:
                            print(f"Error en API para {rel_path}: {e}")
            except Exception as e:
                print(f"Error procesando archivo {file_path}: {e}")
                pass
                
    if needs_update or len(current_files) != len(cache):
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(current_files, f)
        print(f"✅ Embeddings guardados. Total archivos indexados: {len(current_files)}")
    else:
        print("✅ Embeddings al día.")
        
    return current_files

def search_vault(client: genai.Client, query: str, top_k: int = 3, threshold: float = 0.60) -> str:
    if not os.path.exists(CACHE_FILE):
        return ""
        
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cache = json.load(f)
    except Exception:
        return ""
        
    if not cache:
        return ""
        
    try:
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=query,
        )
        query_embedding = np.array(response.embeddings[0].values)
    except Exception as e:
        print(f"Error al embed query: {e}")
        return ""
        
    results = []
    for rel_path, data in cache.items():
        doc_emb = np.array(data['embedding'])
        # Coseno de similitud
        sim = np.dot(query_embedding, doc_emb) / (np.linalg.norm(query_embedding) * np.linalg.norm(doc_emb))
        results.append((sim, rel_path, data['content']))
        
    results.sort(key=lambda x: x[0], reverse=True)
    top_results = results[:top_k]
    
    if not top_results:
        return ""
        
    best_sim = top_results[0][0]
    print(f"🔍 Mejor similitud: {best_sim:.3f} ({top_results[0][1]})")
    
    if best_sim < threshold:
        print("Ignorando bóveda (debajo del umbral de relevancia).")
        return ""
        
    context_str = ""
    for sim, rel_path, content in top_results:
        if sim >= threshold:
            context_str += f"\n\n--- Archivo: {rel_path} ---\n{content}"
        
    return context_str
