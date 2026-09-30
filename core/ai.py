import os
import glob
import time
from google import genai
from google.genai import types

from core.config import GEMINI_API_KEY

# Nuevo cliente moderno de Google GenAI
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = 'gemini-2.5-flash'

# Diccionario en memoria para guardar las sesiones de chat por usuario
chat_sessions = {}

def load_vault_context():
    """Lee todos los archivos .md de la bóveda para darle contexto a la IA."""
    vault_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../cerebro'))
    context = ""
    search_paths = [
        os.path.join(vault_path, "02-Conocimiento", "**", "*.md"),
        os.path.join(vault_path, "01-Proyectos", "**", "*.md")
    ]
    
    files_read = 0
    for path in search_paths:
        for file_path in glob.glob(path, recursive=True):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    context += f"\n\n--- Archivo: {os.path.basename(file_path)} ---\n{content}"
                    files_read += 1
            except Exception:
                pass
    print(f"📚 [Vault Context] Se leyeron {files_read} archivos de la bóveda.")
    return context

def get_or_create_chat(user_id: int):
    if user_id not in chat_sessions:
        print(f"🆕 Iniciando nueva sesión de chat conversacional (Con Búsqueda Web) para usuario {user_id}")
        system_instruction = (
            "Eres el asistente de ideación y arquitecto de conocimiento personal del usuario. "
            "Tu misión es ayudar a desarrollar y pulir ideas. Para ello, TIENES DOS FUENTES PRINCIPALES DE VERDAD:\n"
            "1. La Bóveda del Usuario: Conecta sus ideas con los proyectos que ya tiene (contexto más abajo).\n"
            "2. Internet (Google Search): Si el usuario te pide investigar algo que no está en la bóveda, o necesitas información "
            "actualizada para desarrollar su idea, TIENES PERMISO Y DEBES usar tu herramienta de búsqueda. "
            "Cuando busques en la web, prioriza siempre resultados de foros especializados, Reddit y documentación técnica oficial.\n\n"
            "En lugar de simplemente guardar la información, debes debatir, hacer preguntas inteligentes para profundizar en la idea. "
            "Sé conciso, directo y técnico (tu personalidad se basa en los archivos AGENTS.md).\n\n"
            "A continuación, tienes el contexto actual de toda la bóveda del usuario:\n"
            f"{load_vault_context()}"
        )
        
        chat = client.chats.create(
            model=MODEL_NAME,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=[{"google_search": {}}],  # Activamos Google Search Grounding
                temperature=0.7
            )
        )
        chat_sessions[user_id] = chat
    return chat_sessions[user_id]

def process_audio_to_text(audio_path: str) -> str:
    """Sube el archivo de audio a Gemini y pide únicamente su transcripción literal."""
    try:
        print(f"📡 [Gemini Audio] Subiendo archivo usando nuevo SDK: {audio_path}")
        # Subimos el archivo a la nube de Gemini temporalmente
        audio_file = client.files.upload(file=audio_path)
        prompt = "Escucha este audio y devuelve ÚNICAMENTE la transcripción exacta de lo que digo. No agregues nada más."
        
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[prompt, audio_file]
        )
        
        # Limpieza
        client.files.delete(name=audio_file.name)
        return response.text.strip()
    except Exception as e:
        print(f"❌ [Gemini Audio Error] {e}")
        return None

def chat_with_gemini(user_id: int, text: str) -> dict:
    """Envía un mensaje al historial de chat del usuario y devuelve métricas."""
    try:
        chat = get_or_create_chat(user_id)
        
        start_time = time.time()
        response = chat.send_message(text)
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
        print(f"❌ [Gemini Chat Error] {e}")
        return None

def generate_final_markdown(user_id: int) -> dict:
    """Resume la conversación en un Markdown final y devuelve las métricas."""
    try:
        if user_id not in chat_sessions:
            return None
        chat = chat_sessions[user_id]
        prompt = (
            "La sesión de ideación ha concluido y el usuario quiere guardar esta idea. "
            "Con base en TODA la conversación que hemos tenido en este chat (tanto mis ideas como lo que investigaste en internet), "
            "resume y estructura la idea desarrollada en un documento Markdown profesional listo para guardarse en Obsidian.\n"
            "1. Añade un título (con #), viñetas para las ideas principales y negritas para resaltar conceptos clave.\n"
            "2. Incluye una sección de 'Conexiones' si identificas que esta idea se relaciona con otros archivos de la bóveda.\n"
            "3. Incluye una sección de 'Fuentes Externas' si usaste información de Google o Reddit durante el debate.\n"
            "4. Devuelve SOLO el texto en formato Markdown sin presentaciones."
        )
        print(f"🧠 [Gemini Summarize] Generando documento final para usuario {user_id}...")
        
        start_time = time.time()
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
