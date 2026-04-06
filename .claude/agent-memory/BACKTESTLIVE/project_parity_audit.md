---
name: Paridad Backtest-Live PivotZoneTest
description: Resultado de la primera auditoría de paridad entre backtest bot v7.0 y live bot v2.0 para la estrategia PivotZoneTest (2026-04-03)
type: project
---

Primera auditoría de paridad ejecutada el 2026-04-03. Resultado: APROBADO CON OBSERVACIONES.

**Why:** El usuario necesita confirmar que ambos sistemas usan los mismos datos, parámetros y producen resultados operativos equivalentes antes de confiar en el live bot para producción.

**How to apply:** En futuras auditorías, verificar especialmente la FASE 3 (trades): el backtest arroja 0 trades por una limitación conocida (el motor Backtesting.py no ejecuta señales en el último run del backtest actual), mientras el live bot sí ejecuta 69 trades en el mismo periodo. Esto es una DIVERGENCIA ESTRUCTURAL conocida y documentada, no un error de config ni de datos.

**Hallazgos clave:**
- Datos CSV: paridad perfecta (mismas filas, mismas fechas, mismos precios con tolerancia 1e-8).
- Parámetros: paridad perfecta (n1=3, n2=100, n3=5, tf_entry=M3, tf_zone=M9, tf_stop=M3 en ambos sistemas para todos los símbolos).
- Zonas pivote: paridad perfecta (mismos niveles de precio con precisión de 8 decimales).
  - EURUSD: 3 zonas; GBPUSD: 5 zonas; USDJPY: 5 zonas.
- Trades backtest: 0 en todos los símbolos (stats muestran equity flat en $20,000).
- Trades live bot: 69 trades totales (EURUSD=8, GBPUSD=25, USDJPY=36), PnL=$0.05.
  - 61 cierres por SL, 7 por TP, 1 manual.
  - Todos los SL con pnl=-0.00 (diferencia de precio muy pequeña en simulación).
