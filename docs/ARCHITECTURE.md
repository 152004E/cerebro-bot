# Architecture & Project Structure (cerebro-bot)

## Rol del Proyecto
`cerebro-bot` es el orquestador principal del pipeline de captura automatizada del ecosistema **Cerebro**. Escrito en Python, se encarga de interceptar mensajes, contextualizarlos mediante IA y enviarlos al repositorio de Obsidian.

## Componentes Clave
1. **Interfaz de Entrada (Telegram Bot)**: Recibe notas de texto y audio desde la cuenta del usuario.
2. **Procesamiento de Audio & IA**: Envía audios a Gemini para transcripción y actúa como agente crítico para procesar la idea.
3. **Módulo RAG**: Inyecta conocimiento previo buscando contexto en la bóveda de Obsidian.
4. **Almacenamiento (GitHub API)**: Convierte la respuesta final en Markdown nativo y la empuja (push) directamente al repositorio remoto de la bóveda de Obsidian, específicamente a la carpeta `03-Bandeja_de_Entrada`.

## Estructura de Directorios
```text
cerebro-bot/
├── core/                # Módulos principales (Telegram, IA, GitHub, RAG)
├── docs/                # Reglas y Arquitectura
├── main.py              # Punto de entrada principal de la aplicación
├── requirements.txt     # Dependencias del proyecto
├── telemetry.json       # Registro de telemetría y métricas
└── .venv/               # Entorno virtual de Python
```
