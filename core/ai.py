import os
import time
from google import genai
from google.genai import types
from groq import Groq
from duckduckgo_search import DDGS

from core.config import (
    GEMINI_API_KEY, GEMINI_FAST_MODEL, GEMINI_PRO_MODEL,
    GROQ_API_KEY, GROQ_MODEL, GROQ_AUDIO_MODEL
)
import core.rag as rag

# Clientes de IA
client = genai.Client(api_key=GEMINI_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Diccionario en memoria para guardar las sesiones de chat por usuario
chat_sessions = {}

# Sincronizar embeddings al iniciar el módulo
vault_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../cerebro'))

if not os.path.exists(vault_path):
    print("☁️ [Nube] Bóveda local no encontrada. Clonando repositorio privado usando GITHUB_TOKEN...")
    import subprocess
    from core.config import GITHUB_TOKEN, GITHUB_REPO
    clone_dir = "/tmp/cerebro_vault"
    
    repo_url = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"
    if not os.path.exists(clone_dir):
        subprocess.run(["git", "clone", "--depth", "1", repo_url, clone_dir])
    else:
        subprocess.run(["git", "pull"], cwd=clone_dir)
        
    vault_path = clone_dir

try:
    rag.sync_vault_embeddings(client, vault_path)
except Exception as e:
    print(f"Error sincronizando embeddings: {e}")

def get_or_create_chat(user_id: int):
    if user_id not in chat_sessions:
        print(f"🆕 Iniciando nueva sesión de chat conversacional para usuario {user_id}")
        system_instruction = (
            "Eres el asistente de ideación y arquitecto de conocimiento personal del usuario.\n"
            "Tu misión es ayudar a desarrollar y pulir ideas basándote en:\n"
            "1. La Bóveda del Usuario: El usuario te enviará fragmentos de su bóveda como contexto de ser necesario.\n"
            "2. Tu Conocimiento Base: Usa tu inteligencia para aportar conceptos técnicos, arquitecturas y soluciones avanzadas.\n\n"
            "En lugar de simplemente guardar la información, debes debatir, hacer preguntas inteligentes para profundizar en la idea. "
            "Sé conciso, directo y técnico."
        )
        
        chat = client.chats.create(
            model=GEMINI_FAST_MODEL,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7
            )
        )
        chat_sessions[user_id] = chat
    return chat_sessions[user_id]

def process_audio_to_text(audio_path: str) -> str:
    """Transcribe usando Groq Whisper v3 Turbo (~0.3s) con fallback a Gemini."""
    # 1. Intento primario con Groq (Ultra rápido y 0 consumo de tokens en Google)
    if groq_client:
        try:
            start_whisper = time.time()
            with open(audio_path, "rb") as audio_file:
                transcription = groq_client.audio.transcriptions.create(
                    model=GROQ_AUDIO_MODEL,
                    file=(os.path.basename(audio_path), audio_file.read()),
                    response_format="text"
                )
            if transcription and transcription.strip():
                lat = time.time() - start_whisper
                print(f"⚡ [Groq Whisper] Transcrito en {lat:.2f}s: {transcription.strip()[:40]}...")
                return transcription.strip()
        except Exception as e_groq:
            print(f"⚠️ [Groq Whisper Fallback] Error en Groq ({e_groq}), recurriendo a Gemini...")

    # 2. Fallback a Google Gemini
    try:
        print(f"📡 [Gemini Audio Fallback] Subiendo archivo a Google: {audio_path}")
        audio_file = client.files.upload(file=audio_path)
        prompt = "Escucha este audio y devuelve ÚNICAMENTE la transcripción exacta de lo que digo. No agregues nada más."
        
        response = client.models.generate_content(
            model=GEMINI_FAST_MODEL,
            contents=[prompt, audio_file]
        )
        
        client.files.delete(name=audio_file.name)
        return response.text.strip()
    except Exception as e:
        print(f"❌ [Gemini Audio Error] {e}")
        return None

def chat_with_gemini(user_id: int, text: str, mode: str = "normal") -> dict:
    """Envía un mensaje al historial de chat del usuario y devuelve métricas."""
    try:
        chat = get_or_create_chat(user_id)
        
        if mode == "ingles":
            print(f"🇬🇧 [Teacher English] Procesando palabra o consulta sin interferencia RAG...")
            final_prompt = (
                f"[MODO TEACHER ENGLISH]\n"
                f"Actúa como profesor y traductor de inglés americano conciso, dinámico y didáctico.\n"
                f"Analiza la siguiente palabra o frase enviada por el usuario: '{text}'.\n\n"
                f"ESTRUCTURA DE RESPUESTA OBLIGATORIA (máximo 4-5 líneas):\n"
                f"• Categoría: [Verbo / Sustantivo / Adjetivo / Frase / etc.]\n"
                f"• Significado: [Traducción y explicación clara en español]\n"
                f"• Ejemplo: [1 oración natural en inglés con su traducción al español]\n"
                f"• Pronunciación: [Pronunciación figurada fonética y consejos de sonido estilo americano]\n\n"
                f"REGLA CRÍTICA: Termina SIEMPRE tu mensaje con la etiqueta exacta: [MODO_TRADUCTOR]"
            )
        else:
            # Búsqueda RAG normal para ideación
            context = rag.search_vault(client, text)
            final_prompt = text
            if context:
                print(f"📚 Inyectando contexto RAG...")
                final_prompt = f"--- Contexto recuperado de la Bóveda ---\n{context}\n\n--- Mensaje del Usuario ---\n{text}"
            else:
                print(f"🌐 Sin contexto RAG, confiando en conocimiento general/Google Search...")
        
        start_time = time.time()
        response = chat.send_message(final_prompt)
        latency = time.time() - start_time
        
        tokens = 0
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            tokens = response.usage_metadata.total_token_count
            
        return {
            "text": response.text,
            "tokens": tokens,
            "latency": latency
        }
    except Exception as e:
        error_msg = str(e)
        print(f"❌ [Gemini Chat Error] {error_msg}")
        
        # Fallback anticaídas inmediato a Groq
        if groq_client:
            try:
                print(f"⚡ [Groq Chat Fallback] Activando {GROQ_MODEL} tras fallo en Gemini...")
                start_fb = time.time()
                sys_inst = (
                    "Eres un asistente de ideación y conocimiento técnico directo y conciso. Estilo cavernícola (directo al grano, sin rodeos)."
                    if mode != "ingles" else
                    "Actúa como profesor y traductor de inglés americano conciso y didáctico. Termina siempre con [MODO_TRADUCTOR]."
                )
                groq_resp = groq_client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": sys_inst},
                        {"role": "user", "content": final_prompt}
                    ],
                    temperature=0.7
                )
                lat_fb = time.time() - start_fb
                tok_fb = groq_resp.usage.total_tokens if hasattr(groq_resp, "usage") and groq_resp.usage else 0
                return {
                    "text": groq_resp.choices[0].message.content,
                    "tokens": tok_fb,
                    "latency": lat_fb,
                    "fallback": "groq"
                }
            except Exception as e_groq_fb:
                print(f"❌ [Groq Fallback Error] {e_groq_fb}")

        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg.upper():
            return {"error": "rate_limit"}
        return None

def generate_final_markdown(user_id: int, is_traductor: bool = False) -> dict:
    """Resume la conversación en un Markdown final y devuelve las métricas."""
    try:
        if user_id not in chat_sessions:
            return None
        chat = chat_sessions[user_id]
        
        if is_traductor:
            prompt = (
                "La sesión de ideación ha concluido. Resume la conversación en formato Markdown. "
                "IMPORTANTE: Como esta sesión fue del MODO TRADUCTOR de Inglés, "
                "extrae la palabra y devuélvela con la siguiente estructura exacta, SIN modificar la etiqueta YAML:\n"
                "```yaml\n"
                "target_file: 02-Conocimiento/Idiomas/Ingles/Vocabulario.md\n"
                "file_mode: append\n"
                "```\n"
                "### [Categoría: Ej. Verbo / Sustantivo]\n"
                "- **[Palabra]**: [Significado/Traducción] (/pronunciación/)\n"
                "  - Detalles (Pasados o Usos): ...\n"
                "  - Ejemplo: ..."
            )
        else:
            prompt = (
                "La sesión de ideación ha concluido y el usuario quiere guardar esta idea. "
                "Con base en TODA la conversación que hemos tenido en este chat (tanto mis ideas como lo que investigaste en internet), "
                "resume y estructura la idea desarrollada en un documento Markdown profesional listo para guardarse en Obsidian.\n"
                "1. Añade un título (con #), viñetas para las ideas principales y negritas para resaltar conceptos clave.\n"
                "2. Incluye una sección de 'Conexiones' si identificas que esta idea se relaciona con otros archivos de la bóveda.\n"
                "3. Incluye una sección de 'Fuentes Externas' si usaste información de Google o Reddit durante el debate.\n"
                "4. Devuelve SOLO el texto en formato Markdown sin presentaciones."
            )
            
        print(f"🧠 [Gemini Summarize] Generando documento final con {GEMINI_PRO_MODEL} para usuario {user_id}...")
        
        start_time = time.time()
        try:
            history = chat.get_history()
            contents = list(history) + [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
            response = client.models.generate_content(
                model=GEMINI_PRO_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(temperature=0.2)
            )
        except Exception as e_pro:
            print(f"⚠️ [Gemini Pro Fallback] Falló {GEMINI_PRO_MODEL} ({e_pro}), usando chat fallback...")
            response = chat.send_message(prompt)
            
        latency = time.time() - start_time
        
        tokens = 0
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            tokens = response.usage_metadata.total_token_count
            
        # Limpiamos la sesión para la próxima vez
        del chat_sessions[user_id]
        
        return {
            "text": response.text,
            "tokens": tokens,
            "latency": latency
        }
    except Exception as e:
        print(f"❌ [Gemini Summarize Error] {e}")
        return None

def search_internet_ddg(query: str, max_results=5) -> str:
    """Busca en DDG (último año) y formatea los resultados."""
    try:
        results = DDGS().text(query, timelimit='y', max_results=max_results)
        if not results:
            return "No se encontró información."
        
        context = "--- RESULTADOS DE INTERNET ---\n"
        for r in results:
            context += f"Título: {r.get('title')}\nInfo: {r.get('body')}\nURL: {r.get('href')}\n\n"
        return context
    except Exception as e:
        print(f"Error DDG: {e}")
        return "Error en el buscador web."

def research_with_grok(query: str, web_context: str) -> dict:
    """Agente Investigador impulsado por Groq"""
    if not groq_client:
        return {"text": "⚠️ GROQ_API_KEY no configurada. Añádela en .env o Render."}
        
    prompt = (
        f"Eres un investigador tecnológico estricto y directo. Analiza esta información de internet sobre '{query}':\n"
        f"{web_context}\n\n"
        "REGLAS:\n"
        "1. Resume las ideas principales basándote SOLO en el contexto dado.\n"
        "2. Identifica el consenso (qué opina la mayoría).\n"
        "3. Lista las URL de las fuentes consultadas al final.\n"
        "4. No uses saludos ni introducciones corporativas. Sé de estilo 'cavernícola' (directo y al grano)."
    )
    
    try:
        start_time = time.time()
        chat_completion = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=GROQ_MODEL, 
            temperature=0.3,
        )
        latency = time.time() - start_time
        return {
            "text": chat_completion.choices[0].message.content,
            "latency": latency
        }
    except Exception as e:
        print(f"Error Groq: {e}")
        return {"text": "⚠️ Error conectando con el agente investigador (Groq)."}
