import google.generativeai as genai
from core.config import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)

# Utilizamos el modelo multimodal más veloz
model = genai.GenerativeModel('gemini-1.5-flash-latest')

def process_audio_to_markdown(audio_path: str) -> str:
    """
    Sube el archivo de audio a Gemini y le pide que lo transcriba
    y le dé formato Markdown estructurado.
    """
    try:
        audio_file = genai.upload_file(path=audio_path)
        
        prompt = (
            "Eres un asistente de conocimiento experto. Escucha esta nota de voz. "
            "1. Transcribe lo que digo.\n"
            "2. Estructúralo en un documento Markdown profesional.\n"
            "3. Añade un título (con #), viñetas para las ideas principales, y negritas para resaltar conceptos clave.\n"
            "4. Devuelve SOLO el texto en formato Markdown, sin presentaciones ni despedidas."
        )
        
        response = model.generate_content([prompt, audio_file])
        genai.delete_file(audio_file.name)
        
        return response.text
    except Exception as e:
        print(f"Error procesando audio con Gemini: {e}")
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
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error procesando texto con Gemini: {e}")
        return None
