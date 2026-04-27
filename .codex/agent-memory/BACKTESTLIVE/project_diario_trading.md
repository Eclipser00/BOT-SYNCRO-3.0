---
name: Diario de Operaciones BOT-SYNCRO 3.0
description: Estructura y estado del Diario.md de operaciones: fechas cubiertas, limitaciones conocidas de los logs, y patrones recurrentes observados
type: project
---

Diario.md creado el 2026-04-16 en `c:\Users\Administrator\Desktop\BOT-SYNCRO-3.0\Diario.md`.

Cubre los dias 14/04/2026 y 15/04/2026 (primer y segundo dia de operacion en produccion).

**Why:** El bot_events.jsonl solo tiene datos hasta 2026-04-13 (no registro eventos del 14 ni 15). Todo el detalle operativo del 14-15 viene exclusivamente del production.log. Los precios de cierre de las posiciones NO estan disponibles en production.log — el log solo registra el cursor_updated (timestamp MT5 del cierre) pero no el precio. Para obtener precios de cierre habria que leer el historial de MT5 directamente o esperar que el bot_events.jsonl se actualice.

**How to apply:** Al generar entradas futuras del Diario, verificar primero si bot_events.jsonl ha sido actualizado con nuevos eventos (fills con precio de cierre). Si no, anotar precios de cierre como "no disponible en logs". El campo `cursor_updated` en CLOSED_TRADES_RESULT da el timestamp UTC del cierre pero no el precio.

**Patrones observados:**
- Cierres ultrarapidos (<10 min) ocurrieron en PWR 116 (8 min) y CARR 2456 (6 min) el dia 15 — posiblemente SL activado por spread al abrir.
- CARR mostro cascada de zonas bajistas: 2 zonas distintas quebradas en el mismo dia.
- El SL calculado por la estrategia puede ser rechazado por MT5 por distancia minima — el broker ajusta automaticamente y el bot lo registra como WARNING.
- BKR recibio 4 senales BUY consecutivas bloqueadas por margen antes de poder entrar — el margen se libera cuando las posiciones existentes cierran.
- La primera orden del dia 14 arranca con cursor en ticket 135652398 (cierre previo de XOM del dia 13).
