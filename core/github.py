from github import Github
from core.config import GITHUB_TOKEN, GITHUB_REPO
from datetime import datetime
import re

g = Github(GITHUB_TOKEN)
repo = g.get_repo(GITHUB_REPO)

def upload_to_obsidian(markdown_content: str) -> str:
    """
    Sube el contenido markdown al repositorio de GitHub de Obsidian
    en la carpeta 03-Bandeja_de_Entrada.
    """
    try:
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        
        # Extraer el primer H1 para usarlo como nombre de archivo si existe
        title_match = re.search(r'^#\s+(.+)$', markdown_content, re.MULTILINE)
        if title_match:
            clean_title = re.sub(r'[^a-zA-Z0-9_\- ]', '', title_match.group(1)).strip()
            clean_title = clean_title.replace(' ', '_')
            filename = f"{clean_title}_{timestamp}.md"
        else:
            filename = f"Nota_de_Voz_{timestamp}.md"
            
        file_path = f"03-Bandeja_de_Entrada/{filename}"
        commit_message = f"🤖 Bot: Nueva nota inyectada ({timestamp})"
        
        print(f"📦 [GitHub] Destino: {GITHUB_REPO}/{file_path}")
        print(f"📝 [GitHub] Mensaje de commit: {commit_message}")
        
        repo.create_file(
            path=file_path,
            message=commit_message,
            content=markdown_content,
            branch="main"
        )
        
        print(f"🚀 [GitHub] Commit y push realizados con éxito en branch 'main'")
        return file_path
    except Exception as e:
        print(f"❌ [GitHub Error] Falló al crear archivo en GitHub: {e}")
        return None
