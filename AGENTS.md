# Pipeline de Desarrollo con Agentes

SE ENCUENTRANE EN /.codex

Este proyecto usa un sistema de agentes especializados que se ejecutan en orden cada vez que se programa. Claude debe seguir este flujo siempre, sin saltarse pasos ni reordenarlos.

---

## Flujo de ejecución

### Paso 1 — CONTEXTUALIZADOR *(solo si el usuario lo pide)*

- Conecta con NotebookLM vía MCP para extraer contexto relevante.
- Si el usuario no lo solicita explícitamente, **omitir este paso** y continuar en el paso 2.
- Prerequisito: MCP de NotebookLM configurado (`claude mcp add notebooklm npx notebooklm-mcp@latest`).

### Paso 2 — EVALUADOR

- Analiza el código y diagnostica el problema o requerimiento.
- No modifica nada. Solo lee, entiende y propone.
- **Entrada en el loop de fallos:** Si TESTER devuelve fallos, EVALUADOR recibe el reporte de tests (con archivos, líneas y errores) y vuelve a diagnosticar desde ahí.

### Paso 3 — PLANEADOR

- Convierte el diagnóstico del EVALUADOR en un plan de acción numerado.
- No avanza hasta que el usuario valide el plan.

### Paso 4 — AUDITORMINIMALISTA

- Evalúa el plan del PLANEADOR y verifica que la solución propuesta sea la más simple posible.
- Detecta cambios innecesarios, sobreingeniería o modificaciones que van más allá del mínimo requerido.
- **Si el plan es minimal y directo** → aprueba y continúa al paso 5.
- **Si detecta complejidad evitable** → propone una versión reducida del plan y vuelve al **paso 3** para que PLANEADOR lo revise.
- No modifica código. Solo evalúa el plan.

### Paso 5 — WRITER

- Ejecuta el plan aprobado. Es el único agente que modifica código.
- Un paso del plan, un cambio. Confirma con el usuario cuando el plan lo requiera.

### Paso 6 — REFACTORIZADOR

- Revisa el código recién escrito en busca de deuda técnica, código muerto y duplicados.
- Genera un informe de refactorización validado por el usuario.
- **Si el usuario aprueba cambios:** WRITER aplica el informe antes de continuar al paso 7.

### Paso 7 — TESTER

- Crea tests para los cambios y ejecuta **toda la suite completa**.
- **Si todos los tests pasan** → continuar al paso 8.
- **Si algún test falla** → generar reporte detallado (test, archivo, línea, error, causa) y volver al **paso 2** con ese reporte como entrada.

### Paso 8 — EVALUADORFINAL

- Audita el trabajo de todos los agentes anteriores.
- Verifica que el código, plan, tests y refactorización son coherentes entre sí.
- Emite veredicto: APROBADO / CON OBSERVACIONES / REQUIERE CORRECCIÓN.
- Si hay correcciones → indica qué agente debe intervenir y vuelve al paso correspondiente.
- Si está aprobado → continuar al paso 9.

### Paso 9 — DOCUMENTADOR

- Lee el proyecto completo y genera el `.md` de documentación actualizado.
- Presenta el documento al usuario para validación antes de guardarlo.
- Al finalizar, elimina los logs temporales de `/logs`.

---

## Reglas generales

- **Ningún agente puede saltarse su turno.** El orden es obligatorio.
- **Solo WRITER modifica código fuente.** El resto lee, analiza, planifica, testea o documenta.
- **Sin plan aprobado, WRITER no escribe.** Si no hay plan del PLANEADOR, WRITER se detiene y lo solicita.
- **El loop de fallos puede repetirse** todas las veces que sea necesario hasta que TESTER pase al 100%.
- **Los logs en `/logs` son temporales.** Solo existen entre el inicio del ciclo y el veredicto del EVALUADORFINAL.

---

## Agentes disponibles

| Agente             | Rol                                                  | Modifica código        |
| ------------------ | ---------------------------------------------------- | ----------------------- |
| CONTEXTUALIZADOR   | Extrae contexto de NotebookLM                        | No                      |
| EVALUADOR          | Diagnostica problemas                                | No                      |
| PLANEADOR          | Diseña el plan de acción                           | No                      |
| AUDITORMINIMALISTA | Verifica que la solución sea la más simple posible | No                      |
| WRITER             | Escribe y modifica código                           | Sí                     |
| REFACTORIZADOR     | Detecta deuda técnica                               | No (genera informe)     |
| TESTER             | Crea y ejecuta tests                                 | Solo archivos de test   |
| EVALUADORFINAL     | Audita el trabajo completo                           | No                      |
| DOCUMENTADOR       | Genera documentación del proyecto                   | Solo el `.md` de docs |
