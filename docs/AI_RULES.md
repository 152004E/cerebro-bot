# Reglas & Guías (AI_RULES) para cerebro-bot

## Comunicación
- Modo cavernícola: técnico, sin relleno.
- Código/commits: claridad normal.

## Convenciones de Código (Python)
- **Entorno Virtual**: Uso obligatorio de `.venv`. Todas las dependencias se instalan con `pip` y se documentan en `requirements.txt`. Prohibido el uso indiscriminado de paquetes globales.
- **Tipado Estricto**: Todo el código Python debe llevar type hints (`def func(param: str) -> bool:`).
- **Simplicidad**: Evitar abstracciones prematuras. Preferir código funcional y claro.
- **Manejo de Errores**: Capturar excepciones específicas. No silenciar errores con `except Exception: pass`.

## Reglas del Ecosistema
- **Gestión de Versiones**: **El agente NUNCA hace commits.** Solo el usuario comitea. Prohibido ejecutar `git commit`, `git push`, etc. Solo se permiten consultas locales como `git status`.
- **Documentación y Artefactos**: Todos los planes de arquitectura se generan con comandos nativos y diagramas de estados/flujos se escriben en `mermaid`.
