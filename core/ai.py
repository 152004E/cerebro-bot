import os
import time
from google import genai
from google.genai import types

from core.config import GEMINI_API_KEY
import core.rag as rag

# Nuevo cliente moderno de Google GenAI
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = 'gemini-3.5-flash-lite'

# Diccionario en memoria para guardar las sesiones de chat por usuario
chat_sessions = {}

# Sincronizar embeddings al iniciar el módulo
vault_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../cerebro'))
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
            model=MODEL_NAME,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
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
        
        # Búsqueda RAG
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
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg.upper():
            return {"error": "rate_limit"}
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
