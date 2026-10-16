import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO", "152004E/cerebro")

GEMINI_FAST_MODEL: str = os.getenv("GEMINI_FAST_MODEL", "gemini-3.5-flash-lite")
GEMINI_PRO_MODEL: str = os.getenv("GEMINI_PRO_MODEL", "gemini-3.5-flash")

if not all([TELEGRAM_TOKEN, GEMINI_API_KEY, GITHUB_TOKEN]):
    raise ValueError("Faltan variables de entorno en el archivo .env")
