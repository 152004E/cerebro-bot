import google.generativeai as genai
from core.config import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)

# Utilizamos el modelo multimodal más veloz
model = genai.GenerativeModel('gemini-2.5-flash')

def process_audio_to_markdown(audio_path: str) -> str:
    """
    Sube el archivo de audio a Gemini y le pide que lo transcriba
    y le dé formato Markdown estructurado.
    """
    try:
        print(f"📡 [Gemini Audio] Subiendo archivo a la nube de Google: {audio_path}")
        audio_file = genai.upload_file(path=audio_path)
        print(f"✅ [Gemini Audio] Archivo subido con ID: {audio_file.name}")
        
        prompt = (
            "Eres un asistente de conocimiento experto. Escucha esta nota de voz. "
            "1. Transcribe lo que digo.\n"
            "2. Estructúralo en un documento Markdown profesional.\n"
            "3. Añade un título (con #), viñetas para las ideas principales, y negritas para resaltar conceptos clave.\n"
            "4. Devuelve SOLO el texto en formato Markdown, sin presentaciones ni despedidas."
        )
        
        print("🧠 [Gemini Audio] Esperando respuesta del modelo multimodal...")
        response = model.generate_content([prompt, audio_file])
        
        print("🧹 [Gemini Audio] Eliminando archivo de los servidores de Google...")
        genai.delete_file(audio_file.name)
        
        return response.text
    except Exception as e:
        print(f"❌ [Gemini Audio Error] {e}")
        return None

def process_text_to_markdown(text: str) -> str:
    """
    Pide a Gemini que le dé formato Markdown a una nota de texto.
    """
    try:
        prompt = (
            "Eres un asistente de conocimiento experto. El usuario envió esta nota de texto cruda:\n\n"
            f"\"{text}\"\n\n"
            "1. Mejora la redacción si es necesario.\n"
            "2. Estructúrala en un documento Markdown profesional.\n"
            "3. Añade un título (con #), viñetas para ideas principales, y negritas para resaltar.\n"
            "4. Devuelve SOLO el texto en formato Markdown, sin presentaciones."
        )
        print("🧠 [Gemini Text] Solicitando estructuración a Gemini 2.5 Flash...")
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"❌ [Gemini Text Error] {e}")
        return None
