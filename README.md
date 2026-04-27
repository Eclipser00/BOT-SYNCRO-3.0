# Bot Syncro 3.0 — last_trading_bot_v2.0_pivot_zone_syncro

## Qué hace

Bot de trading algorítmico que opera en MetaTrader 5 usando una estrategia de ruptura de zonas pivote. Detecta zonas de precio construidas sobre pivotes de velas, entra cuando el precio rompe una de esas zonas y gestiona la posición con SL/TP estructurales. El SL inicial nace dentro de la zona rota y puede moverse una sola vez con break-even estructural por pivote; no hay trailing continuo. Soporta modo producción (conexión MT5 real) y modo desarrollo (replay con CSV histórico y broker simulado).

## Stack

- **Lenguaje**: Python 3.10+
- **Broker**: MetaTrader 5 (`MetaTrader5==5.0.5430`)
- **Análisis técnico**: `ta-lib==0.6.8`, `pandas==2.3.3`, `numpy==2.2.6`
- **Visualización**: `bokeh==3.4.1`
- **Tests**: `pytest==9.0.1`
- **Otros**: `python-dateutil`, `pytz`, `tzdata`, `colorama`

## Estructura

```
bot syncro 3.0 (claude)/
├── last_trading_bot_v2.0_pivot_zone_syncro/   # Proyecto principal del bot
│   ├── config.py                               # Configuración única del bot (fuente de verdad)
│   ├── requirements.txt                        # Dependencias del entorno
│   ├── bot_trading/                            # Paquete principal
│   │   ├── main.py                             # Punto de entrada y construcción del bot
│   │   ├── replay_runner.py                    # Runner determinista para desarrollo/CSV
│   │   ├── visualizer.py                       # Entrypoint de visualización manual
│   │   ├── domain/
│   │   │   └── entities.py                     # Entidades de dominio (dataclasses)
│   │   ├── application/
│   │   │   ├── engine/
│   │   │   │   ├── bot_engine.py               # Motor principal (TradingBot)
│   │   │   │   ├── order_executor.py           # Ejecución y registro de órdenes
│   │   │   │   └── signals.py                  # Modelos Signal y SignalType
│   │   │   ├── strategies/
│   │   │   │   ├── base.py                     # Clase base abstracta Strategy
│   │   │   │   └── pivot_zone_test_strategy.py # Estrategia principal
│   │   │   ├── risk_management.py              # RiskManager (drawdown por nivel)
│   │   │   ├── strategy_registry.py            # Registro de estrategias y magic numbers
│   │   │   └── utils/
│   │   │       └── event_logger.py             # Logger JSONL de eventos
│   │   ├── infrastructure/
│   │   │   ├── mt5_client.py                   # BrokerClient protocol + MetaTrader5Client
│   │   │   └── data_fetcher.py                 # MarketDataService + DevelopmentCsvDataProvider
│   │   └── visualization/
│   │       ├── live_plot_service.py             # AutoVisualizerService (HTML por símbolo)
│   │       ├── plot_bokeh.py                   # Renderizador Bokeh
│   │       ├── data_source.py                  # Fuentes de velas para el visualizador
│   │       ├── event_reader.py                 # Lectura de eventos JSONL
│   │       ├── state_store.py                  # Persistencia de estado del visualizador
│   │       └── runner.py                       # Runner del visualizador standalone
│   ├── data_development/                       # CSV históricos para modo desarrollo
│   ├── logs/                                   # Logs de ejecución y pivote
│   ├── plots/                                  # Eventos JSONL, HTMLs y cursores
│   └── tests/                                  # Suite completa de tests
├── shared/
│   └── instrument_specs.json                   # Especificaciones de instrumentos (tick_size, etc.)
└── backtest bot v7.0 syncro/                   # Módulo separado de backtesting
```

## Estado actual de salidas runtime

El proyecto principal `last_trading_bot_v2.0_pivot_zone_syncro` usa una única carpeta runtime interna:

- `last_trading_bot_v2.0_pivot_zone_syncro/plots/bot_events.jsonl`
- `last_trading_bot_v2.0_pivot_zone_syncro/plots/closed_trades_cursor.json`
- `last_trading_bot_v2.0_pivot_zone_syncro/plots/visualizer{SYMBOL}.html`

El last trading bot no debe crear, leer ni priorizar `outputs/bot_events.jsonl` en la raíz del workspace. Los resolvers del visualizador apuntan solo a la raíz del bot y no consultan la carpeta padre. Al arrancar, `_clean_plots()` borra HTMLs anteriores y reinicia `plots/bot_events.jsonl`, pero conserva `plots/closed_trades_cursor.json`.

## Módulos

### `config.py`
- **Propósito**: Fuente de verdad única para toda la configuración del bot. Define perfiles por entorno (production/development) y expone `settings` como instancia global.
- **Funciones/Clases**:
  - `BotConfig` → Dataclass raíz que agrupa todos los bloques de configuración.
  - `BrokerConfig` → Parámetros del broker: uso de broker real o simulado, reintentos, credenciales MT5.
  - `LoggingConfig` → Nivel de log, escritura a fichero, rutas de log y comportamiento del visualizador.
  - `RiskConfig` → Límites de drawdown global, por símbolo y por estrategia; balance inicial de referencia.
  - `SymbolConfigEntry` → Configuración por símbolo: nombre, timeframe mínimo y overrides de parámetros de estrategia.
  - `StrategyConfig` → Parámetros de la estrategia: nombre, timeframes, n1/n2/n3, size_pct, lista blanca de símbolos.
  - `LoopConfig` → Periodo de vela base, espera tras cierre, flag para omitir sleep en simulación.
  - `DataConfig` → Modo de datos (production/development), carpeta CSV, lookback de bootstrap.
  - `TemporalConfig` → Hardening UTC: cursor de trades cerrados, solapamiento, lookback inicial.
  - `load_settings(env)` → Devuelve copia desacoplada de la configuración del entorno solicitado.
  - `validate_config(cfg)` → Valida coherencia antes de arrancar y lanza `ValueError` si hay errores.

### `bot_trading/main.py`
- **Propósito**: Punto de entrada. Construye todos los componentes, configura logging, selecciona broker (real o simulado) y arranca el bucle sincronizado.
- **Clases**:
  - `FakeBroker` → Broker simulado en memoria. Simula apertura/cierre de posiciones usando datos OHLC del CSV. Mantiene `open_positions`, `closed_trades` y `pending_orders`. Implementa el mismo interfaz que `MetaTrader5Client`.
- **Función principal**:
  - `main()` → Lee `settings`, llama a `validate_config`, construye `MarketDataService`, `RiskManager`, `OrderExecutor`, instancias de estrategias y `TradingBot`, y lanza `run_synchronized`.

### `bot_trading/replay_runner.py`
- **Propósito**: Runner determinista que fuerza el entorno a `development` y ejecuta `main()` para reproducir el bot con datos CSV. Útil para comparación de paridad con el backtest.

### `bot_trading/domain/entities.py`
- **Propósito**: Define todas las entidades de dominio como dataclasses. No contiene lógica.
- **Entidades**:
  - `SymbolConfig` → Nombre, timeframe mínimo y overrides de parámetros por símbolo.
  - `AccountInfo` → Balance, equity, margen usado y margen libre.
  - `RiskLimits` → Límites de drawdown y porcentaje máximo de margen.
  - `Position` → Posición abierta: símbolo, volumen, entry, SL, TP, estrategia, hora de apertura, magic number.
  - `TradeRecord` → Trade cerrado: símb., estrategia, tiempos, precios, volumen, PnL, tickets de deal.
  - `OrderRequest` → Solicitud de orden al broker: símbolo, volumen, tipo, SL, TP, magic number, metadatos de trazabilidad.
  - `OrderResult` → Resultado de orden: éxito, ID, fill price, mensaje de error.
  - `PendingOrder` → Orden limit/stop pendiente para vincular brackets SL/TP.

### `bot_trading/application/engine/bot_engine.py`
- **Propósito**: Motor central (`TradingBot`). Coordina el ciclo completo: sincroniza estado del broker, valida riesgo, obtiene datos, ejecuta estrategias y despacha señales.
- **Clase `TradingBot`**:
  - `sync_clock_with_broker()` → Calcula offset de reloj entre bot y broker usando múltiples muestras y mediana para reducir ruido.
  - `run_once()` → Ejecuta un ciclo completo: sincroniza posiciones, actualiza historial, valida riesgo global, itera símbolos y estrategias, despacha señales al `OrderExecutor`.
  - `run_synchronized(...)` → Bucle principal. Espera el cierre de la vela base y lanza `run_once()` en cada ciclo.

### `bot_trading/application/engine/order_executor.py`
- **Propósito**: Encapsula el envío de órdenes al broker y el registro de posiciones locales.
- **Clase `OrderExecutor`**:
  - `execute_order(order_request)` → Envía la orden al broker, registra `order_submit` y `order_fill` en el log de eventos, y actualiza `open_positions`.
  - `has_open_position(symbol, strategy_name, magic_number)` → Comprueba si ya existe una posición abierta para el par símbolo+magic_number.
  - `close_position(...)` → Construye y envía la orden de cierre.

### `bot_trading/application/engine/signals.py`
- **Propósito**: Modelos de señal que las estrategias devuelven al motor.
- **Tipos**:
  - `SignalType` → Enum: `BUY`, `SELL`, `CLOSE`, `HOLD`.
  - `Signal` → Dataclass con símbolo, nombre de estrategia, timeframe, tipo, tamaño, SL y TP.

### `bot_trading/application/strategies/base.py`
- **Propósito**: Clase base abstracta `Strategy` que define el contrato `generate_signals(data_by_timeframe)`.

### `bot_trading/application/strategies/pivot_zone_test_strategy.py`
- **Propósito**: Estrategia principal. Construye zonas pivote, detecta rupturas y calcula entradas con SL/TP por zona.
- **Clase `PivotZoneTestStrategy`**:
  - `generate_signals(data_by_timeframe)` → Método principal. Recibe datos por timeframe, actualiza zonas, sincroniza estado con broker y devuelve señales `BUY`/`SELL` o lista vacía.
  - Lógica interna:
    - Detecta pivotes de 3 velas en `TF_zone` (M9) y calcula anchura con ATR(14).
    - Construye y valida zonas: distancia mínima entre zonas (`n1 * ancho`), pivotes mínimos para validar (`n3`).
    - Detecta pivotes en `TF_stop` (M3) para calcular el SL inicial dentro de la zona rota.
    - Con posición abierta, aplica break-even estructural por pivote una sola vez: BUY mueve el SL al primer `pivot_min` posterior por encima del entry; SELL al primer `pivot_max` posterior por debajo del entry.
    - Busca breakout de precio en la última vela de `TF_entry` (M3).
    - Selecciona zona objetivo (la más cercana en dirección del trade) para el TP.
    - Calcula lotaje mediante `size_pct` sobre el equity de la cuenta, ajustado ±20% por distancia del stop.
    - Con posición abierta: gestiona SL/TP nativo en MT5 o brackets simulados en FakeBroker, aplica el break-even estructural por pivote una sola vez y aplica TP adaptativo si aparece una zona mejor.

### `bot_trading/application/risk_management.py`
- **Propósito**: Evalúa límites de drawdown antes de operar.
- **Clase `RiskManager`**:
  - `check_bot_risk_limits(trades)` → Valida drawdown global contra `dd_global`.
  - `check_symbol_risk_limits(symbol, trades)` → Valida drawdown del símbolo contra `dd_por_activo`.
  - `check_strategy_risk_limits(strategy, trades)` → Valida drawdown de la estrategia contra `dd_por_estrategia`.
  - `check_margin_limits(account_info, required_margin)` → Valida que el margen usado no supere `max_margin_usage_percent`.

### `bot_trading/application/strategy_registry.py`
- **Propósito**: Asigna y resuelve Magic Numbers únicos por estrategia (hash MD5 del nombre, int32 positivo).
- **Clase `StrategyRegistry`**:
  - `register_strategy(name)` → Registra la estrategia y devuelve su magic number. Detecta y resuelve colisiones.
  - `get_magic_number(name)` → Devuelve el magic number de una estrategia registrada.
  - `get_strategy_name(magic)` → Lookup inverso: magic number → nombre de estrategia.

### `bot_trading/application/utils/event_logger.py`
- **Propósito**: Escribe eventos del bot en formato JSONL en `plots/bot_events.jsonl`. Errores de escritura se silencian para no interrumpir el bot.
- **Clase `EventLogger`**:
  - `log(payload)` → Serializa el payload normalizado (tipos, campos opcionales de zona pivote) y lo añade al fichero.

### `bot_trading/infrastructure/mt5_client.py`
- **Propósito**: Define el protocolo `BrokerClient` (interface) e implementa `MetaTrader5Client` para la conexión real con MT5.
- **Clase `MetaTrader5Client`**:
  - `connect()` / `disconnect()` → Gestiona la sesión con la terminal MT5.
  - `get_ohlcv(symbol, timeframe, start, end)` → Descarga barras OHLCV y las devuelve como DataFrame.
  - `send_market_order(order_request)` → Envía orden de mercado con reintentos y normalización de stops.
  - `get_open_positions(magic)` → Devuelve posiciones abiertas filtradas por magic number.
  - `get_closed_trades(since, until)` → Devuelve historial de deals cerrados con cursor persistente para evitar duplicados.
  - `get_account_info()` → Devuelve `AccountInfo` con balance, equity y márgenes.
  - `get_server_time()` → Devuelve la hora del servidor MT5 en UTC.

### `bot_trading/infrastructure/data_fetcher.py`
- **Propósito**: Abstrae la obtención de datos de mercado para producción y desarrollo.
- **Clases**:
  - `MarketDataService` → Orquesta la obtención de datos; delega en `ProductionDataProvider` o `DevelopmentCsvDataProvider` según el modo.
  - `ProductionDataProvider` → Obtiene OHLCV desde MT5 con lookback de bootstrap configurable.
  - `DevelopmentCsvDataProvider` → Lee CSV desde `data_development/`, avanza una vela por iteración y resamplea los timeframes necesarios por símbolo.

### `bot_trading/visualization/live_plot_service.py`
- **Propósito**: Servicio de visualización automático integrado al loop. Genera y refresca HTMLs Bokeh por símbolo.
- **Clases**:
  - `AutoVisualizerService` → Mantiene estado M3 por símbolo, lee eventos JSONL y zonas pivote del log, y renderiza un HTML por ticker en `plots/`.
  - `resolve_bot_events_path(root, path)` → Resuelve la ruta del fichero de eventos dentro de la raíz del bot.

### `bot_trading/visualization/plot_bokeh.py`
- **Propósito**: Renderiza el gráfico de velas con zonas pivote, trades y señales usando Bokeh. Devuelve HTML estático.

### `bot_trading/visualization/event_reader.py`
- **Propósito**: Parsea líneas del JSONL de eventos y del log de pivote para alimentar el visualizador.

### `bot_trading/visualization/state_store.py`
- **Propósito**: Persiste el estado del visualizador (cursor de lectura, última vela procesada) entre ciclos para soportar `start_from_end`.

### `shared/instrument_specs.json`
- **Propósito**: Especificaciones estáticas de instrumentos (tick_size, tick_value, etc.) usadas por la estrategia cuando el broker no puede devolverlas en tiempo de ejecución.

## Configuración

Todos los parámetros se editan en `config.py`. Los valores más relevantes:

| Variable | Descripción |
|----------|-------------|
| `ACTIVE_ENV` | `"development"` (FakeBroker + CSV) o `"production"` (MT5 real) |
| `BrokerConfig.use_real_broker` | `True` activa MT5; `False` usa FakeBroker |
| `BrokerConfig.load_env_credentials` | Si `True`, lee `MT5_SERVER`, `MT5_LOGIN`, `MT5_PASSWORD` del entorno |
| `RiskConfig.dd_global` | Drawdown máximo global (%) |
| `RiskConfig.max_margin_usage_percent` | Porcentaje máximo de margen permitido |
| `StrategyConfig.n1` | Separación mínima entre zonas = `n1 * ancho_zona` |
| `StrategyConfig.n2` | Ancho de zona = `ATR(14) * (n2/100)` |
| `StrategyConfig.n3` | Pivotes mínimos para validar una zona |
| `StrategyConfig.size_pct` | Riesgo base por operación (0.1 = 1% del equity) |
| `LoopConfig.timeframe_minutes` | Periodo de la vela base en minutos (default: 3) |
| `DataConfig.data_development_dir` | Carpeta con CSVs históricos para desarrollo |

Credenciales MT5 en producción: variables de entorno `MT5_SERVER`, `MT5_LOGIN`, `MT5_PASSWORD` (no guardar en git).

## Cómo ejecutar

```bash
# Instalar dependencias
cd last_trading_bot_v2.0_pivot_zone_syncro
pip install -r requirements.txt

# Modo desarrollo (CSV + FakeBroker): editar ACTIVE_ENV = "development" en config.py
python config.py
# o directamente:
python -m bot_trading.replay_runner

# Modo producción (MT5 real): editar ACTIVE_ENV = "production" en config.py
# y configurar variables de entorno MT5_SERVER, MT5_LOGIN, MT5_PASSWORD
python config.py

# Ejecutar tests
pytest tests/

# Visualizador standalone (opcional)
python -m bot_trading.visualizer
```

---

## Diagramas de flujo

```
BOT SYNCRO 3.0
│
├─ 1. ARRANQUE
│  │
│  ├─ Leer `config.py`
│  ├─ Validar configuración
│  ├─ Configurar logs
│  ├─ Construir componentes
│  │  │
│  │  ├─ Broker
│  │  │  ├─ `MetaTrader5Client` si es producción
│  │  │  └─ `FakeBroker` si es development/testing
│  │  │
│  │  ├─ `MarketDataService`
│  │  ├─ `RiskManager`
│  │  ├─ `OrderExecutor`
│  │  ├─ Estrategias
│  │  │  └─ `PivotZoneTestStrategy`
│  │  ├─ Símbolos
│  │  └─ Visualizador automático opcional
│  │
│  └─ Si usa broker real
│     └─ Sincronizar reloj con MT5
│
├─ 2. ENTRADA AL BUCLE PRINCIPAL
│  │
│  └─ `run_synchronized(...)`
│     │
│     ├─ Esperar cierre de vela base
│     ├─ Esperar segundos extra configurados
│     └─ Lanzar `run_once()`
│
├─ 3. CICLO `run_once()`
│  │
│  ├─ Sincronizar estado de órdenes/posiciones abiertas
│  ├─ Actualizar historial de trades cerrados
│  ├─ Validar riesgo global del bot
│  │  ├─ Si falla → bloquear ciclo
│  │  └─ Si pasa → seguir
│  │
│  └─ Recorrer símbolos uno por uno
│     │
│     ├─ Validar riesgo por símbolo
│     │  ├─ Si falla → saltar símbolo
│     │  └─ Si pasa → seguir
│     │
│     ├─ Calcular timeframes requeridos por estrategias
│     ├─ Filtrar timeframes compatibles con el símbolo
│     └─ Pedir datos al `MarketDataService`
│
├─ 4. OBTENCIÓN DE DATOS
│  │
│  ├─ En producción
│  │  └─ Obtener OHLCV desde MT5
│  │
│  ├─ En development
│  │  ├─ Leer CSV de `data_development`
│  │  ├─ Avanzar una vela por iteración
│  │  └─ Resamplear timeframes necesarios
│  │
│  └─ Resultado
│     └─ `data_by_timeframe`
│        ├─ TF entry = M3
│        ├─ TF zone = M9
│        └─ TF stop = M3
│
├─ 5. SI ES MODO SIMULADO
│  │
│  ├─ Tomar OHLC de la última vela
│  ├─ Simular si SL o TP habrían sido tocados
│  ├─ Generar cierres sintéticos si corresponde
│  └─ Emitir eventos de fill / position
│
├─ 6. EJECUCIÓN DE ESTRATEGIAS
│  │
│  └─ Para cada estrategia
│     │
│     ├─ Validar riesgo por estrategia
│     │  ├─ Si falla → saltar estrategia
│     │  └─ Si pasa → seguir
│     │
│     └─ Ejecutar `PivotZoneTestStrategy.generate_signals(...)`
│
├─ 7. LÓGICA DE `PivotZoneTestStrategy`
│  │
│  ├─ Validar que existan los timeframes necesarios
│  ├─ Detectar símbolo desde los DataFrames
│  ├─ Resolver parámetros del símbolo
│  │  ├─ `n1`
│  │  ├─ `n2`
│  │  ├─ `n3`
│  │  └─ `size_pct`
│  │
│  ├─ Preparar series cerradas
│  │  ├─ `df_entry`
│  │  ├─ `df_zone`
│  │  └─ `df_stop`
│  │
│  ├─ Actualizar estado interno del símbolo
│  │
│  ├─ Procesar timeframe de zonas (`TF_zone`)
│  │  ├─ Detectar pivotes
│  │  ├─ Construir zonas pivote
│  │  ├─ Validar zonas
│  │  └─ Guardar nuevas zonas válidas
│  │
│  ├─ Procesar timeframe de stop (`TF_stop`)
│  │  └─ Detectar pivotes usados para SL inicial y break-even estructural
│  │
│  ├─ Sincronizar estado con broker
│  │  ├─ Si hay posición abierta
│  │  │  ├─ Recuperar dirección
│  │  │  ├─ Recuperar entry
│  │  │  ├─ Recuperar SL activo
│  │  │  └─ Recuperar TP activo
│  │  └─ Si no hay posición
│  │     └─ Limpiar estado local
│  │
│  ├─ ¿Hay posición abierta?
│  │  │
│  │  ├─ Sí
│  │  │  ├─ Gestionar SL/TP nativo o brackets según broker
│  │  │  ├─ Mantener SL/TP
│  │  │  ├─ Aplicar break-even estructural por pivote una sola vez
│  │  │  ├─ Aplicar TP adaptativo si aparece mejor zona
│  │  │  └─ No generar nueva entrada
│  │  │
│  │  └─ No
│  │     ├─ Buscar breakout de una zona guardada
│  │     ├─ Si no hay breakout → no hay señal
│  │     ├─ Si hay breakout:
│  │     │  ├─ Identificar zona rota
│  │     │  ├─ Identificar dirección
│  │     │  │  ├─ LONG
│  │     │  │  └─ SHORT
│  │     │  ├─ Elegir zona objetivo
│  │     │  ├─ Calcular precio de entrada
│  │     │  ├─ Buscar pivote válido para stop
│  │     │  ├─ Calcular TP en borde de zona objetivo
│  │     │  ├─ Validar coherencia SL < entry < TP o viceversa
│  │     │  ├─ Calcular lotaje por riesgo
│  │     │  ├─ Emitir evento `signal`
│  │     │  └─ Devolver señal BUY o SELL
│
├─ 8. GESTIÓN DE LA SEÑAL EN EL MOTOR
│  │
│  ├─ Obtener magic number de la estrategia
│  ├─ Recorrer señales generadas
│  │
│  ├─ Si señal es BUY/SELL
│  │  ├─ Verificar si ya existe posición abierta
│  │  │  ├─ Sí → ignorar señal
│  │  │  └─ No → seguir
│  │  ├─ Validar límites de margen
│  │  ├─ Construir `OrderRequest`
│  │  └─ Enviar a `OrderExecutor.execute_order()`
│  │
│  ├─ Si señal es CLOSE
│  │  ├─ Verificar que exista posición
│  │  └─ Enviar cierre a `OrderExecutor`
│  │
│  └─ Si no es una señal operable
│     └─ Ignorar
│
├─ 9. `OrderExecutor`
│  │
│  ├─ Recibir `OrderRequest`
│  ├─ Llamar al broker
│  │  └─ `send_market_order(...)`
│  ├─ Si la orden sale bien
│  │  ├─ Registrar posición local
│  │  ├─ Emitir eventos
│  │  └─ Dejar trazabilidad
│  └─ Si falla
│     └─ Registrar error en logs
│
├─ 10. BROKER
│  │
│  ├─ Broker real (`MetaTrader5Client`)
│  │  ├─ Conectar con terminal MT5
│  │  ├─ Obtener datos de mercado
│  │  ├─ Enviar órdenes
│  │  ├─ Consultar posiciones abiertas
│  │  ├─ Consultar trades cerrados
│  │  └─ Normalizar stops para evitar rechazos
│  │
│  └─ Broker simulado (`FakeBroker`)
│     ├─ Simular apertura/cierre
│     ├─ Mantener posiciones en memoria
│     └─ Simular fills con OHLC del CSV
│
├─ 11. SALIDAS DEL SISTEMA
│  │
│  ├─ Logs
│  ├─ Eventos JSONL
│  │  └─ `plots/bot_events.jsonl`
│  ├─ Visualizador HTML
│  │  └─ `plots/visualizer{SYMBOL}.html`
│  └─ Estado interno del bot
│
└─ 12. REPETICIÓN
   │
   ├─ Termina un ciclo
   ├─ Espera la siguiente vela base
   └─ Repite todo el proceso




PIVOTZONETESTSTRATEGY
│
├─ 1. ENTRADA
│  │
│  └─ `generate_signals(data_by_timeframe)`
│     │
│     ├─ Recibe:
│     │  ├─ `df_entry`  -> timeframe de entrada (`M3`)
│     │  ├─ `df_zone`   -> timeframe de zonas (`M9`)
│     │  └─ `df_stop`   -> timeframe de stop (`M3`)
│     │
│     └─ Objetivo:
│        └─ decidir si abrir una operación, mantener la actual o no hacer nada
│
├─ 2. VALIDACIONES INICIALES
│  │
│  ├─ Verificar que los timeframes requeridos existen
│  ├─ Obtener el símbolo desde `df.attrs["symbol"]`
│  ├─ Comprobar si el símbolo está permitido
│  ├─ Resolver parámetros activos del símbolo
│  │  ├─ `n1`
│  │  ├─ `n2`
│  │  ├─ `n3`
│  │  └─ `size_pct`
│  └─ Validar que los DataFrames no estén vacíos
│
├─ 3. PREPARACIÓN DE SERIES
│  │
│  ├─ `df_entry`
│  │  └─ velas cerradas usadas para detectar ruptura
│  │
│  ├─ `df_zone`
│  │  └─ velas cerradas usadas para construir zonas pivote
│  │
│  └─ `df_stop`
│     └─ velas cerradas usadas para encontrar pivotes de stop
│
├─ 4. ESTADO INTERNO POR SÍMBOLO
│  │
│  ├─ Crear o recuperar estado del símbolo
│  ├─ Mantener memoria de:
│  │  ├─ si hay posición
│  │  ├─ dirección actual
│  │  ├─ precio de entrada
│  │  ├─ SL activo
│  │  ├─ TP activo
│  │  ├─ zona rota
│  │  └─ zona objetivo
│  └─ Mantener zonas guardadas y pivotes detectados
│
├─ 5. CONSTRUCCIÓN DE ZONAS
│  │
│  └─ Procesar `TF_zone` (`M9`)
│     │
│     ├─ Detectar pivotes de 3 velas
│     ├─ Calcular anchura de zona
│     ├─ Crear zona superior/inferior
│     ├─ Validar distancia mínima entre zonas
│     ├─ Evitar duplicados o zonas demasiado cercanas
│     ├─ Guardar solo zonas válidas
│     └─ Dejar las zonas listas para buscar rompimientos
│
├─ 6. CONSTRUCCIÓN DE PIVOTES DE STOP
│  │
│  └─ Procesar `TF_stop` (`M3`)
│     │
│     ├─ Detectar pivotes confirmados
│     ├─ Guardarlos por símbolo
│     ├─ Guardar último pivote con precio y hora de confirmación
│     ├─ Usarlos para elegir el stop inicial dentro de la zona rota
│     └─ Usarlos para el break-even estructural una sola vez
│
├─ 7. SINCRONIZACIÓN CON EL BROKER
│  │
│  ├─ Consultar si hay una posición real abierta
│  │
│  ├─ Si sí hay posición abierta
│  │  ├─ Marcar `in_position = True`
│  │  ├─ Recuperar dirección real
│  │  ├─ Recuperar entry real
│  │  ├─ Recuperar SL real
│  │  └─ Recuperar TP real
│  │
│  └─ Si no hay posición real
│     ├─ Cancelar brackets pendientes si hace falta
│     └─ limpiar estado local para no arrastrar información vieja
│
├─ 8. ¿HAY POSICIÓN ABIERTA?
│  │
│  ├─ SÍ
│  │  │
│  │  ├─ No buscar nuevas entradas
│  │  ├─ Gestionar la operación existente
│  │  │
│  │  ├─ Si usa brackets pendientes
│  │  │  ├─ asegurar orden de SL
│  │  │  └─ asegurar orden de TP
│  │  │
│  │  ├─ Si no usa brackets
│  │  │  └─ limpiar pendientes sobrantes
│  │  │
│  │  ├─ Evaluar stop dinámico una sola vez
│  │  │  ├─ no es trailing continuo
│  │  │  ├─ BUY  -> primer `pivot_min` posterior por encima del entry
│  │  │  ├─ SELL -> primer `pivot_max` posterior por debajo del entry
│  │  │  └─ si se aplica, bloquear nuevas actualizaciones del SL
│  │  │
│  │  ├─ Evaluar TP adaptativo
│  │  │  │
│  │  │  ├─ aparece una nueva zona válida a favor del trade
│  │  │  ├─ esa nueva zona queda entre la entrada y el TP actual
│  │  │  ├─ mejora suficiente la distancia al objetivo
│  │  │  └─ entonces mover TP más cerca
│  │  │
│  │  └─ Salida:
│  │     └─ no devuelve nueva señal de entrada
│  │
│  └─ NO
│     │
│     └─ buscar oportunidad de entrada
│
├─ 9. BÚSQUEDA DE BREAKOUT
│  │
│  ├─ Tomar lista de zonas guardadas
│  ├─ Revisar la última vela de entrada
│  ├─ Detectar si el precio rompe una zona
│  │
│  ├─ Si no rompe nada
│  │  └─ return sin señales
│  │
│  └─ Si rompe una zona
│     ├─ identificar la zona rota
│     └─ identificar dirección del breakout
│        ├─ LONG
│        └─ SHORT
│
├─ 10. SELECCIÓN DE OBJETIVO
│  │
│  ├─ Buscar la siguiente zona en dirección del trade
│  ├─ Esa zona será la zona objetivo
│  │
│  ├─ Si no existe zona objetivo
│  │  └─ descartar la entrada
│  │
│  └─ Si existe
│     └─ usar su borde más cercano como TP inicial
│
├─ 11. CÁLCULO DE PRECIOS DE LA OPERACIÓN
│  │
│  ├─ Precio de entrada
│  │  └─ close de la vela actual en `TF_entry`
│  │
│  ├─ Stop loss
│  │  └─ buscar pivote confirmado dentro de la zona rota para SL inicial
│
│  ├─ Stop dinámico una sola vez
│  │  ├─ BUY  -> primer `pivot_min` posterior por encima del entry
│  │  └─ SELL -> primer `pivot_max` posterior por debajo del entry
│  │
│  ├─ Take profit
│  │  └─ borde más cercano de la zona objetivo
│  │
│  └─ Validar coherencia:
│     ├─ LONG  -> `SL < entry < TP`
│     └─ SHORT -> `TP < entry < SL`
│
├─ 12. CÁLCULO DEL TAMAÑO
│  │
│  ├─ Calcular distancia entre entrada y stop
│  ├─ Consultar equity de cuenta
│  ├─ Consultar información del símbolo
│  ├─ Aplicar `size_pct` como riesgo base
│  ├─ Convertir riesgo en lotaje
│  └─ Ajustar a límites válidos del broker
│
├─ 13. FILTRO FINAL
│  │
│  ├─ Si no puede calcular lotaje
│  │  └─ descartar señal
│  │
│  ├─ Si SL/TP no son coherentes
│  │  └─ descartar señal
│  │
│  └─ Si todo es válido
│     └─ seguir
│
├─ 14. EMISIÓN DE SEÑAL
│  │
│  ├─ Emitir evento interno `signal`
│  ├─ Crear objeto `Signal`
│  │  ├─ `BUY` si breakout long
│  │  └─ `SELL` si breakout short
│  │
│  ├─ Incluir:
│  │  ├─ símbolo
│  │  ├─ estrategia
│  │  ├─ timeframe
│  │  ├─ tamaño
│  │  ├─ stop_loss
│  │  └─ take_profit
│  │
│  └─ Devolver lista de señales al motor
│
├─ 15. CONGELACIÓN DEL ESTADO
│  │
│  ├─ Marcar internamente que ya hay posición esperada
│  ├─ Guardar dirección
│  ├─ Guardar zona rota
│  ├─ Guardar zona objetivo
│  ├─ Guardar SL activo
│  ├─ Guardar TP activo
│  ├─ Marcar stop dinámico como no actualizado
│  └─ Dejar preparado el manejo del siguiente ciclo
│
└─ 16. RESULTADO FINAL POSIBLE
   │
   ├─ No hacer nada
   ├─ Gestionar una operación ya abierta
   └─ Generar una nueva señal de compra o venta




8. GESTIÓN DE LA SEÑAL EN EL MOTOR
   │
   ├─ A. La estrategia devuelve una o varias `Signal`
   │  │
   │  ├─ Cada `Signal` ya viene con:
   │  │  ├─ `symbol`
   │  │  ├─ `signal_type` -> BUY / SELL / CLOSE
   │  │  ├─ `size`
   │  │  ├─ `stop_loss`
   │  │  ├─ `take_profit`
   │  │  ├─ `strategy_name`
   │  │  └─ `timeframe`
   │  │
   │  └─ Aquí la estrategia ya ha hecho su trabajo
   │     └─ el motor decide si esa señal se convierte o no en orden
   │
   ├─ B. Obtener `magic_number` de la estrategia
   │  │
   │  ├─ El motor consulta el `StrategyRegistry`
   │  ├─ Cada estrategia tiene un identificador numérico estable
   │  ├─ Ese número se envía al broker con la orden
   │  └─ Sirve para distinguir:
   │     ├─ qué estrategia abrió la posición
   │     ├─ qué posición pertenece a qué lógica
   │     └─ evitar confundir operaciones del mismo símbolo
   │
   │  Ejemplo:
   │  ├─ `PivotZoneTestStrategy` -> magic fijo
   │  └─ clave interna de posición -> `EURUSD_123456789`
   │
   ├─ C. Recorrer las señales una por una
   │  │
   │  └─ El motor no ejecuta "la estrategia" directamente
   │     └─ ejecuta cada `Signal` individualmente
   │
   ├─ D. Si la señal es `BUY` o `SELL`
   │  │
   │  ├─ D1. Verificar si ya existe posición abierta
   │  │  │
   │  │  ├─ Llama a `order_executor.has_open_position(symbol, strategy_name, magic_number)`
   │  │  ├─ La comprobación fuerte se hace por:
   │  │  │  └─ `symbol + magic_number`
   │  │  ├─ Si ya existe, la señal se ignora
   │  │  └─ Objetivo:
   │  │     └─ evitar doble entrada de la misma estrategia en el mismo símbolo
   │  │
   │  │  Ejemplo:
   │  │  ├─ ya hay `EURUSD` abierto por `PivotZoneTest`
   │  │  └─ llega otra señal BUY de `PivotZoneTest`
   │  │     └─ se descarta
   │  │
   │  ├─ D2. Validar límites de margen
   │  │  │
   │  │  ├─ El motor pide `account_info` al broker
   │  │  ├─ Si el broker soporta cálculo de margen requerido:
   │  │  │  ├─ obtiene tick actual
   │  │  │  ├─ estima margen necesario para esa orden
   │  │  │  └─ lo pasa a `RiskManager.check_margin_limits(...)`
   │  │  │
   │  │  ├─ El `RiskManager` revisa dos cosas:
   │  │  │  ├─ que el margen usado actual no supere el límite configurado
   │  │  │  └─ que abrir esta nueva orden no lo haga superar
   │  │  │
   │  │  ├─ También revisa:
   │  │  │  └─ que haya `margin_free` suficiente si el broker pudo estimarlo
   │  │  │
   │  │  └─ Si algo falla:
   │  │     └─ la orden se bloquea antes de enviarse
   │  │
   │  ├─ D3. Construir `OrderRequest`
   │  │  │
   │  │  ├─ Aquí la señal se convierte en una solicitud formal de orden
   │  │  ├─ El motor rellena:
   │  │  │  ├─ `symbol`
   │  │  │  ├─ `volume = signal.size`
   │  │  │  ├─ `order_type = BUY o SELL`
   │  │  │  ├─ `stop_loss`
   │  │  │  ├─ `take_profit`
   │  │  │  ├─ `comment = estrategia + timeframe`
   │  │  │  ├─ `magic_number`
   │  │  │  ├─ `bar_index`
   │  │  │  ├─ `timeframe`
   │  │  │  ├─ `price_ref = close`
   │  │  │  └─ `ts_event`
   │  │  │
   │  │  └─ Esto ya es el paquete que entiende el ejecutor
   │  │
   │  └─ D4. Enviar a `OrderExecutor.execute_order()`
   │     │
   │     ├─ El `OrderExecutor` registra un evento `order_submit`
   │     ├─ Llama al broker:
   │     │  └─ `broker_client.send_market_order(order_request)`
   │     │
   │     ├─ Si el broker rechaza la orden:
   │     │  └─ devuelve `OrderResult(success=False, ...)`
   │     │
   │     ├─ Si el broker acepta:
   │     │  ├─ registra evento `order_fill`
   │     │  ├─ calcula el mejor `fill_price` disponible
   │     │  └─ registra la posición internamente
   │     │
   │     └─ El ejecutor guarda la posición en:
   │        └─ `open_positions[symbol_magic]`
   │
   ├─ E. Si la señal es `CLOSE`
   │  │
   │  ├─ E1. Verificar que exista posición abierta
   │  │  ├─ si no existe -> ignorar
   │  │  └─ si existe -> seguir
   │  │
   │  ├─ E2. Construir `OrderRequest`
   │  │  ├─ `order_type = CLOSE`
   │  │  ├─ `symbol`
   │  │  ├─ `volume`
   │  │  ├─ `magic_number`
   │  │  └─ comentario y trazabilidad
   │  │
   │  └─ E3. Ejecutar cierre
   │     ├─ `OrderExecutor.execute_order(order_request)`
   │     ├─ el broker recibe una orden de cierre
   │     ├─ si sale bien:
   │     │  ├─ se elimina la posición del mapa interno
   │     │  └─ se emite evento `position -> flat`
   │     └─ si falla:
   │        └─ queda logueado como error
   │
   ├─ F. Si la señal no es operable
   │  │
   │  ├─ El motor la ignora
   │  └─ Esto cubre cualquier tipo no previsto o inconsistente
   │
   └─ G. Resultado final de este bloque
   │
   ├─ la señal puede terminar en:
   │  ├─ orden abierta
   │  ├─ orden cerrada
   │  ├─ orden bloqueada por margen
   │  ├─ orden ignorada por posición existente
   │  └─ orden ignorada por tipo no operable
   │
   └─ además deja trazabilidad en:
   ├─ logs
   ├─ `open_positions`
   └─ `plots/bot_events.jsonl`
```
