---
name: Causa raíz - 0 trades en backtest vs 69 trades en live bot
description: La causa real de la diferencia de trades entre backtest y live bot es la ausencia del archivo instrument_specs.json y la falta de defaults en el backtest.
type: project
---

El backtest genera 0 trades porque `size_percent_by_stop()` retorna 0.0 al no encontrar `tick_size`/`tick_value`.

**Raíz:** El archivo `shared/instrument_specs.json` no existe en el proyecto. El backtest (`strategies.py`) intenta leerlo y si falla devuelve `{}`. Sin ese archivo, `tick_size=None` y `tick_value=None`, y `size_percent_by_stop()` en `_BaseLoggedStrategy` retorna `0.0`, lo que bloquea la emisión de la orden en `next()` línea 1952-1954.

**Por qué el live bot sí genera trades:** `FakeBroker._get_symbol_info()` en `main.py` línea 554-565 aplica defaults hardcodeados (`trade_tick_value=10.0`, `trade_tick_size=0.0001`, etc.) cuando el archivo no existe o no tiene los campos requeridos.

**Archivos clave:**
- Backtest: `backtest bot v7.0 syncro/strategies.py` líneas 689-698 (`size_percent_by_stop`) y línea 30 (`_INSTRUMENT_SPECS_PATH`)
- Live bot: `last_trading_bot_v2.0_pivot_zone_syncro/bot_trading/main.py` líneas 554-565 (`FakeBroker._get_symbol_info`)

**Why:** La falta de un archivo `shared/instrument_specs.json` no fue detectada porque el log JSONL (`backtest_events.jsonl`) corresponde a una corrida anterior con parámetros diferentes (n2=60) donde el backtest sí tenía ese archivo o usaba otro mecanismo.

**How to apply:** Al diagnosticar discrepancias de trades entre los dos sistemas, verificar primero si `instrument_specs.json` existe en la ruta esperada por `strategies.py`. La solución mínima es crear ese archivo con los specs de EURUSD, GBPUSD, USDJPY, o modificar `_snapshot_instrument_spec()` para aplicar los mismos defaults que usa `FakeBroker`.
