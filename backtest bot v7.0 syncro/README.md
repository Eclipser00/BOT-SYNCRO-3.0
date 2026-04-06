# Backtest Bot v7.0 Syncro

## Qué hace
Motor de backtesting para estrategias de trading algorítmico sobre datos históricos OHLCV. Simula ejecuciones de órdenes con gestión de riesgo, genera estadísticas de rendimiento y exporta resultados a visualizadores externos.

## Stack
Python 3.x — pandas, numpy, matplotlib, mplfinance. Sin framework de backtesting externo: lógica propia. Datos en CSV local.

## Arquitectura

```
backtest bot v7.0 syncro/
├── main.py                  # Punto de entrada y orquestador del ciclo completo
├── config.py                # Parámetros globales: capital, riesgo, fechas, rutas
├── data/
│   └── loader.py            # Carga y normalización de datos OHLCV desde CSV
├── strategy/
│   ├── signals.py           # Generación de señales de entrada/salida
│   └── filters.py           # Filtros de tendencia y condiciones de mercado
├── engine/
│   ├── simulator.py         # Simulador de órdenes: apertura, SL, TP, cierre
│   └── risk.py              # Cálculo de tamaño de posición y exposición
├── analytics/
│   ├── stats.py             # Métricas: PnL, drawdown, winrate, Sharpe
│   └── report.py            # Generación de reporte final en consola y archivo
├── visualizer/
│   └── chart.py             # Gráficos de curva de equity y operaciones sobre precio
└── logs/
    └── events.csv           # Registro de operaciones simuladas (temporal)
```

`main.py` orquesta la secuencia: carga datos → aplica estrategia → simula órdenes → calcula métricas → exporta. Cada capa depende solo de la anterior, lo que permite reemplazar cualquier módulo sin romper el resto.

## Flujo principal

```
Arranque
└── config.py carga parámetros
    └── loader.py lee CSV y normaliza OHLCV
        └── signals.py + filters.py generan señales por barra
            └── simulator.py itera barra a barra
                ├── risk.py determina tamaño de posición
                ├── Abre orden si hay señal válida
                ├── Evalúa SL / TP en cada barra
                └── Cierra posición cuando se cumple condición
                    └── stats.py acumula resultados
                        └── report.py + chart.py exportan salidas
```

El simulador itera barra a barra para evitar lookahead bias: cada decisión usa solo datos disponibles hasta esa barra. `risk.py` limita la exposición por operación según el capital disponible actualizado. Las salidas se generan solo al finalizar toda la simulación.

## Estrategia y Señales

```
signals.py
├── Indicadores técnicos (medias, RSI, ATR)
├── Condición de entrada long / short
└── Condición de salida por señal contraria

filters.py
├── Filtro de tendencia principal (EMA lenta)
├── Filtro de volatilidad (ATR mínimo)
└── Filtro horario (sesiones activas)
```

`signals.py` genera la señal bruta por barra. `filters.py` actúa como guardián: bloquea entradas en condiciones desfavorables sin tocar la lógica de señal. Separar ambos permite ajustar filtros sin modificar la estrategia base.

## Motor de Simulación

```
simulator.py
├── Estado de posición abierta (precio entrada, tamaño, dirección)
├── Evaluación de SL fijo y TP fijo por barra
├── Gestión de posiciones parciales (si aplica)
└── Registro de cada trade en events.csv

risk.py
├── Capital disponible actualizado tras cada cierre
├── Riesgo por operación (% fijo del capital)
└── Cálculo de unidades según distancia al SL
```

El simulador mantiene un único estado de posición activa; no permite pirámide ni múltiples posiciones simultáneas. El tamaño se recalcula en cada nueva entrada con el capital real del momento, lo que hace que las rachas de pérdidas reduzcan automáticamente la exposición.

## Analytics

```
stats.py
├── PnL acumulado por operación
├── Drawdown máximo (absoluto y porcentual)
├── Winrate, ratio ganancia/pérdida promedio
├── Sharpe ratio anualizado
└── Número de operaciones y duración media

report.py
├── Resumen en consola (tabla de métricas)
└── Exportación a archivo .txt en /logs
```

`stats.py` calcula métricas estándar de evaluación de sistemas. `report.py` las presenta en formato legible para humanos y las guarda para referencia posterior.

## Configuración

| Parámetro | Valor por defecto | Qué controla |
|---|---|---|
| `INITIAL_CAPITAL` | 10000 | Capital inicial de la simulación |
| `RISK_PER_TRADE` | 0.01 | Fracción del capital arriesgada por operación |
| `SL_ATR_MULT` | 1.5 | Multiplicador ATR para Stop Loss |
| `TP_ATR_MULT` | 3.0 | Multiplicador ATR para Take Profit |
| `EMA_FAST` | 20 | Período EMA rápida para señales |
| `EMA_SLOW` | 50 | Período EMA lenta para filtro de tendencia |
| `DATA_PATH` | `data/ohlcv.csv` | Ruta al archivo de datos históricos |
| `START_DATE` | `2020-01-01` | Fecha de inicio del backtest |
| `END_DATE` | `2024-12-31` | Fecha de fin del backtest |
| `COMMISSION` | 0.0005 | Comisión por operación (fracción del valor) |

## Entornos

| Entorno | Datos | Logging | Visualización |
|---|---|---|---|
| Development | CSV local reducido (meses) | Verboso — cada barra | Gráficos en pantalla |
| Production | CSV local completo (años) | Solo trades cerrados | Exportación a archivo |
| Testing | CSV sintético determinista | Capturado en memoria | Desactivada |

## Salidas

- `logs/events.csv` — registro fila por fila de cada operación: entrada, salida, dirección, PnL, duración
- `logs/report.txt` — tabla de métricas al finalizar el backtest
- Consola — resumen de estadísticas y alertas de ejecución
- `visualizer/chart.py` — curva de equity y marcadores de trades sobre el gráfico de precio (PNG o pantalla)
