# Bot Live v2.0 — PivotZoneTest Syncro

## Qué hace
Bot de trading en vivo que opera zonas pivote multi-timeframe sobre MetaTrader 5. Detecta rupturas de precio sobre zonas construidas con pivotes confirmados de 3 velas, envía órdenes bracket (SL/TP) al broker y gestiona la posición abierta hasta el cierre. Puede correr contra MT5 real o contra un broker simulado (FakeBroker) usando CSVs locales sin modificar una sola línea de código.

## Stack
Python 3.x — pandas 2.3.3, numpy 2.2.6, TA-Lib 0.6.8, MetaTrader5 5.0.5430, Bokeh 3.4.1, pytest 9.0.1. Sin ORM ni framework web. Arquitectura propia en capas (domain / application / infrastructure / visualization).

## Estructura

```
last_trading_bot_v2.0_pivot_zone_syncro/
├── config.py                         # Fuente de verdad: perfiles de entorno, validación, arranque
├── requirements.txt                  # Dependencias fijadas con versiones exactas
│
├── bot_trading/
│   ├── main.py                       # Punto de entrada: construye todos los componentes y lanza el loop
│   ├── replay_runner.py              # Runner alternativo para replay de CSV sin loop sincronizado
│   ├── visualizer.py                 # Entrypoint CLI del visualizador independiente
│   │
│   ├── domain/
│   │   └── entities.py               # Dataclasses puras: SymbolConfig, Position, TradeRecord, OrderRequest, RiskLimits
│   │
│   ├── application/
│   │   ├── engine/
│   │   │   ├── bot_engine.py         # TradingBot: orquesta ciclo completo, sincronización de reloj, loop sincronizado
│   │   │   ├── order_executor.py     # OrderExecutor: envía órdenes, registra posiciones, emite eventos JSONL
│   │   │   └── signals.py            # Signal y SignalType (BUY/SELL/CLOSE/HOLD): contrato de señales
│   │   │
│   │   ├── strategies/
│   │   │   ├── base.py               # Protocol Strategy: contrato mínimo que toda estrategia debe implementar
│   │   │   └── pivot_zone_test_strategy.py  # PivotZoneTestStrategy: lógica completa de zonas pivote
│   │   │
│   │   ├── risk_management.py        # RiskManager: drawdown global, por símbolo, por estrategia y margen
│   │   ├── strategy_registry.py      # StrategyRegistry: asigna Magic Numbers únicos por hash MD5
│   │   └── utils/
│   │       └── event_logger.py       # EventLogger: escritura thread-safe de eventos en JSONL
│   │
│   ├── infrastructure/
│   │   ├── mt5_client.py             # BrokerClient (Protocol) + MetaTrader5Client: conexión y órdenes MT5
│   │   └── data_fetcher.py           # MarketDataService + DevelopmentCsvDataProvider: feeds producción/CSV
│   │
│   └── visualization/
│       ├── live_plot_service.py      # AutoVisualizerService: callback del loop que genera HTMLs Bokeh
│       ├── plot_bokeh.py             # BokehPlotBuilder: construcción de gráficos interactivos
│       ├── event_reader.py           # EventReader: parsea bot_events.jsonl y pivot_zones.log
│       ├── state_store.py            # VisualizerStateStore: acumula velas y eventos en memoria
│       ├── data_source.py            # Fuentes de datos para el visualizador
│       └── runner.py                 # Entrypoint de ejecución del visualizador standalone
│
├── data_development/
│   ├── EURUSD.csv                    # Datos históricos M3 para desarrollo
│   ├── GBPUSD.csv
│   └── USDJPY.csv
│
├── outputs/
│   ├── bot_events.jsonl              # Registro de eventos en vivo (órdenes, fills, posiciones)
│   ├── closed_trades_cursor.json     # Cursor persistente para no releer deals ya procesados
│   └── visualizer*.html             # HTMLs Bokeh generados por símbolo
│
├── logs/
│   ├── development.log               # Log general en desarrollo
│   ├── production.log                # Log general en producción
│   └── pivot_zones.log               # Log dedicado de zonas pivote con timestamps de datos
│
└── tests/
    ├── conftest.py
    ├── test_pivot_zone_test_strategy.py
    ├── test_trading_bot.py
    ├── test_order_executor.py
    ├── test_risk_management.py
    ├── test_market_data_service.py
    └── ... (16 archivos de test)
```

El dominio no importa nada de capas superiores. La capa `application` solo conoce el dominio. `infrastructure` y `visualization` dependen de `application`. `main.py` ensambla todo sin que ninguna capa interna sepa de las demás.

## Flujo principal

```
Arranque (config.py / python -m bot_trading.main)
└── validate_config()          — coherencia entre entornos antes de lanzar
    └── _build_broker()        — MetaTrader5Client (prod) o FakeBroker (dev)
        ├── _build_market_data_service()  — feed MT5 real o DevelopmentCsvDataProvider
        ├── _build_risk_manager()         — RiskManager con límites de config.py
        ├── _build_strategies()           — PivotZoneTestStrategy con overrides por símbolo
        ├── _build_auto_visualizer()      — AutoVisualizerService (Bokeh) como callback
        └── TradingBot.run_synchronized()
            └── [cada cierre de vela M3]
                └── run_once()
                    ├── order_executor.sync_state()         — sincroniza posiciones con broker
                    ├── _update_trade_history()             — incorpora trades cerrados
                    ├── risk_manager.check_bot_risk_limits()
                    └── [por cada símbolo]
                        ├── risk_manager.check_symbol_risk_limits()
                        ├── market_data_service.get_data()  — M3 + M9 resampled
                        ├── broker.process_price_tick()     — simula fills SL/TP en dev
                        └── [por cada estrategia]
                            ├── risk_manager.check_strategy_risk_limits()
                            ├── strategy.generate_signals() — PivotZoneTestStrategy
                            └── order_executor.execute_order() — envía a broker
                                └── _emit_event() → bot_events.jsonl
```

`run_synchronized` espera el cierre real de cada vela M3 en producción; en desarrollo avanza por los timestamps del CSV sin dormir (`skip_sleep_when_simulated=True`). El motor detecta automáticamente si hay reloj simulado disponible. Si hay retraso (catch-up), ejecuta los ciclos pendientes en secuencia antes de esperar la siguiente vela.

## Módulos

### bot_engine.py — TradingBot
```
TradingBot
├── run_synchronized()         — loop principal sincronizado con cierres de vela
├── run_once()                 — un ciclo completo: datos → señales → órdenes
├── sync_clock_with_broker()   — alinea el reloj local con la hora del broker (mediana de N muestras)
└── _update_trade_history()    — deduplica y acumula trades cerrados para cálculos de riesgo
```
Coordina todos los componentes sin contener lógica de negocio. `sync_clock_with_broker` toma N muestras y valida un residual final antes de aplicar el offset, abortando el arranque si el desfase supera el umbral configurado.

### order_executor.py — OrderExecutor
```
OrderExecutor
├── execute_order()          — envía al broker y registra posición o cierre
├── sync_state()             — reconstruye open_positions desde el broker real
├── has_open_position()      — lookup directo por symbol+magic_number
├── flush_pending_fills()    — procesa fills diferidos (modo dev)
└── _emit_event()            — escribe order_submit / order_fill / position en JSONL
```
Actúa como capa anticorrupción entre la lógica de señales y el broker concreto. Toda la instrumentación de eventos fluye aquí, garantizando paridad entre modos paper y real.

### signals.py
```
SignalType   — enum BUY / SELL / CLOSE / HOLD
Signal       — dataclass: symbol, strategy_name, timeframe, signal_type, size, stop_loss, take_profit
```
Contrato inmutable entre estrategias y motor. Ninguna estrategia accede directamente al broker; solo emite `Signal`.

### risk_management.py — RiskManager
```
RiskManager
├── check_bot_risk_limits()       — drawdown global sobre todo el historial
├── check_symbol_risk_limits()    — drawdown filtrado por símbolo
├── check_strategy_risk_limits()  — drawdown filtrado por estrategia
└── check_margin_limits()         — margen usado vs. equity; margen libre vs. orden nueva
```
Bloquea el ciclo completo si se supera `dd_global`, o solo el símbolo/estrategia afectado si el límite es granular. El drawdown se calcula desde `initial_balance` para que las pérdidas desde el arranque se computen correctamente aunque no haya un máximo histórico previo.

### strategy_registry.py — StrategyRegistry
```
StrategyRegistry
├── register_strategy()    — genera Magic Number via MD5[:8] % 2^31; detecta colisiones
├── get_magic_number()     — lookup por nombre
└── get_strategy_name()    — lookup inverso por número
```
Garantiza que el mismo nombre de estrategia siempre produce el mismo Magic Number entre reinicios. Esto permite identificar posiciones en el broker incluso si el comentario fue truncado.

### mt5_client.py — MetaTrader5Client / BrokerClient
```
BrokerClient (Protocol)
├── connect()
├── get_ohlcv()
├── send_market_order()
├── get_open_positions()
├── get_closed_trades()
└── get_account_info()

MetaTrader5Client
├── connect()            — inicializa MT5, autentica, valida conexión con reintentos
├── get_ohlcv()          — descarga OHLCV con fallback de símbolo y validación de gaps
├── send_market_order()  — construye request MT5, valida filling mode, maneja errores
└── get_closed_trades()  — recupera deals con cursor persistente para no releer histórico
```
`BrokerClient` es un `Protocol`; cualquier clase que lo satisfaga puede usarse sin herencia. `MetaTrader5Client` implementa reintentos configurables, cache de symbol_info y hardening UTC.

### data_fetcher.py — MarketDataService / DevelopmentCsvDataProvider
```
MarketDataService
└── get_data()           — solicita OHLCV a provider, resamplea a timeframes necesarios

DevelopmentCsvDataProvider
├── get_ohlcv()          — sirve velas del CSV en streaming (avanza barra a barra)
└── get_simulated_now()  — devuelve timestamp actual del CSV para el reloj simulado
```
`MarketDataService` abstrae el origen de datos: en producción delega en MT5, en desarrollo en el CSV. El resampling (M3 → M9) se hace aquí, con semántica `label='right'` para que la vela quede etiquetada en su cierre.

### visualization/
```
AutoVisualizerService
├── on_market_data()     — callback llamado por el motor tras cada ciclo; acumula velas y eventos
└── render()             — construye HTMLs Bokeh por símbolo si ha pasado el intervalo de refresco

BokehPlotBuilder         — construye el gráfico OHLCV con zonas pivote, entradas, SL/TP superpuestos
EventReader              — parsea bot_events.jsonl y pivot_zones.log línea a línea
VisualizerStateStore     — mantiene buffer de velas por símbolo y acumula eventos en memoria
```
El visualizador se registra como `market_data_callback` en `TradingBot`. No bloquea el loop: solo renderiza si han pasado `refresh_seconds` desde el último HTML. Los archivos HTML son autocontenidos y pueden abrirse en cualquier navegador sin servidor.

## Estrategia PivotZoneTest

```
generate_signals(data_by_timeframe)
├── TF_zone (M9) — construcción incremental de zonas
│   ├── _Pivot3CandleState: detecta pivotes con 3 velas confirmadas (sin look-ahead)
│   ├── _PivotZoneProject: acumula pivotes hasta n3 → bloquea zona con ancho = ATR(14) * n2/100
│   └── _saved_zones_by_symbol: lista persistente de zonas válidas separadas por n1 * zone_width
│
├── TF_stop (M3) — stop inicial
│   ├── _Pivot3CandleState: pivotes confirmados en TF_stop
│   └── Stop = último pivot_min (long) o pivot_max (short) previo a la entrada
│
├── TF_entry (M3) — señal de entrada
│   ├── Condición: precio cierra fuera del borde de una zona guardada (breakout)
│   ├── Filtro: sin posición abierta, sin zona rota recientemente, dirección coherente
│   └── Señal BUY o SELL con size calculado por lotaje adaptativo
│
└── Gestión de posición abierta
    ├── TP adaptativo: zona más cercana en dirección del trade (zone-to-zone)
    ├── Si no hay zona destino: fallback a múltiplo del stop
    └── Cierre delegado al broker via órdenes bracket (SL/TP pendientes); sin cierres intrabar
```

**Zonas pivote.** Una zona nace cuando `n3` o más pivotes de 3 velas en TF_zone caen dentro de un rango de ancho `ATR(14) * n2/100`. Dos zonas no pueden estar a menos de `n1 * zone_width` entre sí; la más nueva desplaza a la anterior. Las zonas se construyen de forma incremental: solo se procesan las barras nuevas desde el último ciclo, sin recalcular toda la historia.

**Breakout de entrada.** Se detecta cuando el precio cierra por encima del borde superior (BUY) o por debajo del borde inferior (SELL) de una zona guardada. La estrategia solo entra si no hay posición abierta para ese símbolo con ese Magic Number. No existe lógica de pirámide.

**Lotaje adaptativo.** El volumen se calcula como `risk_fraction = size_pct * 0.1` del equity, modulado en ±20% según la distancia del stop respecto a un stop de referencia del 1%. Esta modulación mantiene el riesgo real estable aunque la distancia al SL varíe entre operaciones.

**TP adaptativo.** El TP apunta a la zona guardada más cercana en la dirección del trade. Si no existe ninguna zona destino, se usa un múltiplo fijo del stop. El TP puede actualizarse si aparece una zona más favorable antes de que el trade cierre.

## FakeBroker vs MetaTrader5Client

| Aspecto | FakeBroker (development) | MetaTrader5Client (production) |
|---|---|---|
| Conexión | Simulada (`connect()` no hace nada real) | MT5 real con reintentos configurables |
| Datos OHLCV | Genera serie lineal de prueba; datos reales vienen de CSV vía `DevelopmentCsvDataProvider` | Descarga desde MT5 con validación de gaps y cache de symbol_info |
| Ejecución de órdenes | Acepta todas; gestiona posiciones en memoria | Envía request a MT5; maneja filling mode y errores de plataforma |
| Fills de SL/TP | `process_price_tick()` evalúa OHLC de cada vela y dispara cierre inmediato o diferido | MT5 gestiona los fills en la plataforma; el bot los detecta al sincronizar historial de deals |
| Historial de trades | Lista en memoria; `get_closed_trades()` devuelve copia | Cursor persistente en `outputs/closed_trades_cursor.json`; relectura con solape de 10 min |
| Credenciales | Ninguna | Variables de entorno `MT5_SERVER`, `MT5_LOGIN`, `MT5_PASSWORD` |
| Hora del broker | `datetime.now(UTC)` | `get_server_time()` usado para sincronizar offset al arranque |
| Margen | `AccountInfo` fijo (equity=20000, margin=0) | Datos reales de la cuenta |

El `BrokerClient` es un `Protocol`, por lo que el resto del sistema no sabe ni le importa cuál de las dos implementaciones está activa. Cambiar de modo es editar `ACTIVE_ENV` en `config.py`.

## Manejo de riesgo

```
RiskManager
├── check_bot_risk_limits()       ← bloquea todo el bot si dd_global se supera
├── check_symbol_risk_limits()    ← bloquea solo el símbolo afectado
├── check_strategy_risk_limits()  ← bloquea solo la estrategia afectada
└── check_margin_limits()         ← bloquea la orden si margen usado > max_margin_usage_percent
                                     o si margen libre < margen requerido por la orden nueva
```

El drawdown se calcula sobre el equity acumulado desde `initial_balance`, con pico histórico actualizado trade a trade. Usar `initial_balance` como punto de partida evita subestimar el drawdown cuando el bot arranca con pérdidas (sin pico previo que sirva de referencia).

**`shared/instrument_specs.json`** es imprescindible para el cálculo de lotaje en FakeBroker y como fallback en MetaTrader5Client. Contiene `trade_tick_value`, `trade_tick_size`, `trade_contract_size`, `volume_min`, `volume_step` y `volume_max` por símbolo. Sin este archivo, la estrategia no puede calcular el volumen correcto en modo desarrollo y cae al mínimo configurable.

## Configuración

### Entorno y broker

| Parámetro | Valor por defecto | Qué controla |
|---|---|---|
| `ACTIVE_ENV` | `"development"` | Perfil activo: `"development"` o `"production"` |
| `broker.use_real_broker` | `False` (dev) / `True` (prod) | MT5 real vs FakeBroker |
| `broker.max_retries` | `3` | Reintentos de conexión/envío antes de fallar |
| `broker.retry_delay` | `0.1` (dev) / `1.0` (prod) | Segundos entre reintentos |
| `broker.load_env_credentials` | `False` (dev) / `True` (prod) | Lee `MT5_SERVER/LOGIN/PASSWORD` del entorno |

### Símbolos

| Parámetro | Valor por defecto | Qué controla |
|---|---|---|
| `symbols[].name` | `EURUSD`, `GBPUSD`, `USDJPY` | Símbolo tal como lo expone el broker |
| `symbols[].min_timeframe` | `M3` | Timeframe mínimo compatible con el símbolo |
| `symbols[].n1` | `3` | Override de separación mínima entre zonas para este símbolo |
| `symbols[].n2` | `100` | Override de multiplicador ATR para ancho de zona |
| `symbols[].n3` | `5` | Override de pivotes mínimos para validar zona |
| `symbols[].size_pct` | `0.1` | Override de riesgo base por operación (0.1 = 1% de la cuenta) |

### Estrategia PivotZoneTest

| Parámetro | Valor por defecto | Qué controla |
|---|---|---|
| `strategy.tf_entry` | `M3` | Timeframe de decisión de entrada y gestión interna |
| `strategy.tf_zone` | `M9` | Timeframe para construir zonas pivote |
| `strategy.tf_stop` | `M3` | Timeframe para pivotes del stop inicial |
| `strategy.n1` | `3` | Separación mínima entre zonas = `n1 * zone_width` |
| `strategy.n2` | `100` | Ancho de zona = `ATR(14) * n2/100` |
| `strategy.n3` | `5` | Pivotes mínimos para bloquear/validar una zona |
| `strategy.size_pct` | `0.05` | Riesgo base de la estrategia (por símbolo, puede ser sobreescrito) |

### Riesgo

| Parámetro | Valor por defecto | Qué controla |
|---|---|---|
| `risk.dd_global` | `30.0` | Drawdown máximo global del bot (%) |
| `risk.dd_por_activo` | `30.0` por símbolo | Drawdown máximo por símbolo (%) |
| `risk.dd_por_estrategia` | `30.0` por estrategia | Drawdown máximo por estrategia (%) |
| `risk.initial_balance` | `20000.0` | Balance de referencia para calcular drawdown |
| `risk.max_margin_usage_percent` | `80.0` | Porcentaje máximo del equity que puede usarse como margen |

### Loop y datos

| Parámetro | Valor por defecto | Qué controla |
|---|---|---|
| `loop.timeframe_minutes` | `3` | Duración de la vela base; define la frecuencia del ciclo |
| `loop.wait_after_close` | `0` | Segundos de espera tras cierre de vela antes de ejecutar |
| `loop.skip_sleep_when_simulated` | `True` (dev) / `False` (prod) | Avanza por timestamps CSV sin dormir en desarrollo |
| `data.data_mode` | `"development"` / `"production"` | Origen de datos: CSV o broker real |
| `data.bootstrap_lookback_days_zone` | `0` (dev) / `15` (prod) | Días de historia para inicializar zonas al arranque |
| `data.csv_base_timeframe` | `M3` | Timeframe base de los CSVs de desarrollo |

### Temporal

| Parámetro | Valor por defecto | Qué controla |
|---|---|---|
| `temporal.strict_utc_mode` | `True` | Normaliza datetimes naive a UTC y emite warnings |
| `temporal.closed_trades_cursor_path` | `outputs/closed_trades_cursor.json` | Ruta del cursor de historial de deals |
| `temporal.closed_trades_overlap_minutes` | `10` | Solape al releer deals para no perder cierres |
| `temporal.closed_trades_initial_lookback_hours` | `72` | Ventana inicial si no existe cursor |
| `temporal.closed_trades_entry_fallback_days` | `7` | Búsqueda histórica de entrada cuando llega un deal de salida sin entrada |

## Entornos

| Aspecto | development | production |
|---|---|---|
| Broker | FakeBroker (simulado en memoria) | MetaTrader5Client (conexión real) |
| Credenciales | Ninguna | Variables de entorno `MT5_*` |
| Datos | `DevelopmentCsvDataProvider` (CSV en `data_development/`) | Feed en vivo de MT5 |
| Loop | Avanza por timestamps del CSV (`skip_sleep_when_simulated=True`) | Espera cierre real de vela M3 |
| Logging | `DEBUG` — logs detallados a `logs/development.log` | `INFO` — logs a `logs/production.log` |
| Bootstrap lookback | `0` días (sin historia previa al CSV) | `15` días (inicializa zonas con histórico real) |
| Visualizador | `visualizer_start_from_end=True` (solo eventos nuevos) | `visualizer_start_from_end=False` (carga historial al reiniciar) |
| Sincronización reloj | No aplica | `sync_clock_with_broker()` obligatoria al arranque; aborta si residual > 2s |

## Salidas

- `outputs/bot_events.jsonl` — log estructurado de eventos en tiempo real: `order_submit`, `order_fill`, `position`. Usado por el visualizador y para auditoría post-sesión.
- `outputs/closed_trades_cursor.json` — cursor de producción que recuerda hasta qué deal se ha leído; evita duplicados entre reinicios.
- `outputs/visualizer{SYMBOL}.html` — gráfico Bokeh interactivo por símbolo con velas OHLCV, zonas pivote superpuestas, marcadores de entrada/salida y niveles SL/TP. Se regenera cada ~15 minutos.
- `logs/development.log` / `logs/production.log` — log general del bot con nivel configurable.
- `logs/pivot_zones.log` — log dedicado de zonas: timestamp de datos, símbolo, nivel de zona y estado (creada / bloqueada / invalidada). Formato minimal para inspección de la lógica de zonas.

## Cómo ejecutar

**Desarrollo (FakeBroker + CSV):**
```
python config.py
```
o
```
python -m bot_trading.main
```
Asegura que `ACTIVE_ENV = "development"` en `config.py`. Los CSV deben estar en `data_development/`.

**Producción (MetaTrader5 real):**
```
# Establecer credenciales en el entorno
set MT5_SERVER=<servidor>
set MT5_LOGIN=<cuenta>
set MT5_PASSWORD=<password>

# Cambiar ACTIVE_ENV = "production" en config.py y ejecutar
python config.py
```

**Visualizador standalone (sin loop del bot):**
```
python -m bot_trading.visualizer
```
Lee `outputs/bot_events.jsonl` y `logs/pivot_zones.log` y genera los HTMLs en `outputs/`.

**Tests:**
```
pytest tests/
```
