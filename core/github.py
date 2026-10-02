from github import Github
from core.config import GITHUB_TOKEN, GITHUB_REPO
from datetime import datetime
import re

g = Github(GITHUB_TOKEN)
repo = g.get_repo(GITHUB_REPO)

def upload_to_obsidian(markdown_content: str) -> str:
    """
    Sube el contenido markdown al repositorio de GitHub de Obsidian
    en la carpeta 03-Bandeja_de_Entrada o hace append si se especifica.
    """
    try:
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        
        # 1. Detectar si la IA nos pide hacer un APPEND en un archivo específico
        target_file_match = re.search(r'target_file:\s*([^\n]+)', markdown_content)
        file_mode_match = re.search(r'file_mode:\s*([^\n]+)', markdown_content)
        
        if target_file_match and file_mode_match and file_mode_match.group(1).strip() == 'append':
            file_path = target_file_match.group(1).strip()
            commit_message = f"🤖 Bot: Actualizando vocabulario ({timestamp})"
            
            # Borrar frontmatter YAML o bloques YAML
            content_to_append = re.sub(r'^```yaml\n.*?\n```\n', '', markdown_content, flags=re.DOTALL).strip()
            content_to_append = re.sub(r'^---\n.*?\n---\n', '', content_to_append, flags=re.DOTALL).strip()
            
            try:
                contents = repo.get_contents(file_path, ref="main")
                new_content = contents.decoded_content.decode("utf-8") + "\n\n" + content_to_append
                repo.update_file(contents.path, commit_message, new_content, contents.sha, branch="main")
                print(f"🚀 [GitHub] Append realizado con éxito en {file_path}")
                return file_path
            except Exception:
                repo.create_file(path=file_path, message=commit_message, content=content_to_append, branch="main")
                print(f"🚀 [GitHub] Archivo creado con éxito en {file_path}")
                return file_path
        
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
