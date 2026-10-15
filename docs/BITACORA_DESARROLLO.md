# Bitácora de Desarrollo

Este archivo sirve para registrar problemas persistentes, decisiones arquitectónicas complejas y el historial de refactorizaciones significativas en `cerebro-bot`.

## [Plantilla de Entrada]
**Fecha:** YYYY-MM-DD
**Tema:** Breve descripción
**Problema/Decisión:**
- Detalle del contexto.
**Solución/Acción:**
- Lo que se implementó.

---

## 2026-10-04
**Tema:** Estandarización de Documentación
**Problema/Decisión:** 
- El proyecto carecía de la carpeta `docs/` para regir el comportamiento del agente y estandarizar la arquitectura, a diferencia de los otros proyectos del ecosistema Cerebro.
**Solución/Acción:**
- Se creó la estructura base (`AI_RULES.md`, `AGENTS.md`, `ARCHITECTURE.md`, `BITACORA_DESARROLLO.md`) adaptando las convenciones originales a los estándares de Python.

---

## 2026-10-15
**Tema:** Disponibilidad Continua (Keep-Alive 24/7) en Render
**Problema/Decisión:**
- En el plan gratuito de Render, el contenedor web entraba en suspensión (*idle spin-down*) tras 15 minutos sin peticiones.
- El tiempo de arranque en frío (*cold start*) superaba los 50 segundos, excediendo el timeout de entrega de Telegram y provocando errores repetitivos `Read timeout expired` en los webhooks.
**Solución/Acción:**
- Se verificó que el endpoint raíz `@app.get("/")` en `main.py` responde en <5ms con status HTTP 200.
- Se configuró y activó un monitor externo en `cron-job.org` programado para enviar peticiones `GET` a `https://mi-cerebro-bot.onrender.com/` cada 10 minutos (`*/10 * * * *`).
- La prueba en vivo arrojó respuesta inmediata (`200 OK`) y el microservicio quedó protegido contra suspensiones, activo 24/7 sin exceder la cuota gratuita de 750 horas de Render.
- Registro técnico detallado en `docs/PLAN_KEEP_ALIVE.md`.

---

## 2026-10-15 (Tarde)
**Tema:** Persistencia y Aislamiento de Modo en Teacher English
**Problema/Decisión:**
- Al presionar *"Guardar Palabra"* en Modo Inglés, la rutina llamaba a `del chat_sessions[user_id]`, borrando la memoria y expulsando al usuario al modo general de debate.
- Al enviar la siguiente palabra (ej: *"outgoing"*), el motor RAG general inyectaba notas técnicas de la bóveda (webhooks salientes de arquitectura), confundiendo vocabulario cotidiano con discusión de software.
- Al iniciar el modo, se invocaba innecesariamente a Gemini con un prompt vacío que renderizaba botones de guardado prematuros sin haber enviado aún ninguna palabra.
**Solución/Acción:**
- Se renombró el botón del menú principal a `🇬🇧 Teacher English`.
- Se implementó una máquina de estados de usuario (`user_modes`) para mantener al usuario en `Teacher English` indefinidamente hasta orden explícita.
- Se configuró bienvenida estática limpia (sin llamada a Gemini ni botones prematuros de guardado).
- Se aisló `chat_with_gemini(..., mode="ingles")` omitiendo la búsqueda RAG de proyectos.
- Se agregó salida controlada mediante botón inline `❌ Salir de Teacher English`, comando `/salir` y palabras clave (*"salir"*, *"exit"*).
- Registro en `walkthrough.md`.
