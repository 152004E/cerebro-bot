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
