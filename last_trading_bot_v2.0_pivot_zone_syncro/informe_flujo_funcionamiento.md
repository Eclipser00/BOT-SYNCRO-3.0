# Informe de flujo de funcionamiento - last trading bot

Fecha de analisis: 2026-04-18

Proyecto analizado: `last_trading_bot_v2.0_pivot_zone_syncro`

Metodo usado:

- EVALUADOR general/production: lectura de configuracion, entrypoints, motor, broker real, ordenes, riesgo y logs.
- EVALUADOR development/replay: lectura de replay, CSV provider, FakeBroker, visualizador, eventos y tests.
- EVALUADOR sincronizacion/estrategia: comparacion entre production y development, codigo compartido y divergencias que pueden cambiar resultados.
- PLANIFICADOR: consolidacion de hallazgos en este informe.
- DOCUMENTADOR: guardado de este documento `.md`.

No se modifico codigo fuente. No se ejecutaron tests porque el pedido es documental.

---

## 1. General

### 1.1. Idea principal del sistema

`last_trading_bot_v2.0_pivot_zone_syncro` es un bot de trading multi-capa que opera la estrategia `PivotZoneTest` sobre MetaTrader 5 o sobre un entorno de replay local.

La arquitectura esta construida para que production y development usen casi el mismo flujo:

```text
config.py
  -> bot_trading.main.main()
    -> validar configuracion
    -> configurar logs y limpiar plots
    -> construir broker
    -> construir servicio de datos
    -> construir risk manager
    -> construir order executor
    -> construir estrategias
    -> construir simbolos
    -> construir visualizador automatico
    -> construir TradingBot
    -> run_synchronized()
      -> run_once()
        -> sync_state()
        -> actualizar trades cerrados desde broker/ledger
        -> validar riesgo
        -> obtener OHLCV
        -> generar senales
        -> validar posicion/margen
        -> ejecutar orden
        -> emitir eventos
        -> actualizar visualizador
```

La separacion de capas es clara:

- `config.py`: fuente de verdad de entornos, simbolos, estrategia, riesgo, datos, logs y parametros temporales.
- `bot_trading/main.py`: ensamblador. Decide que implementacion concreta se usa.
- `domain/entities.py`: dataclasses puras.
- `application/engine`: motor, senales y ejecutor de ordenes.
- `application/strategies`: estrategia `PivotZoneTest`.
- `application/risk_management.py`: control de drawdown y margen.
- `infrastructure`: proveedores de datos, cliente MT5 y ledger persistente de trades cerrados.
- `visualization`: lectura de eventos, estado de plot y HTML Bokeh.
- `tests`: cobertura de motor, estrategia, providers, ordenes, visualizador, riesgo y replay.

### 1.2. Entry points

Hay tres formas principales de arrancar el sistema:

```text
python config.py
```

Ejecuta el bot normal usando `ACTIVE_ENV` actual.

```text
python -m bot_trading.main
```

Tambien ejecuta el bot normal.

```text
python -m bot_trading.replay_runner
```

Fuerza `development` antes de importar `bot_trading.main`, lo que lo convierte en el entrypoint mas seguro para replay fuera de mercado.

Para visualizacion standalone:

```text
python -m bot_trading.visualizer
```

### 1.3. Configuracion actual detectada

En `config.py`, `ACTIVE_ENV` esta actualmente en:

```python
ACTIVE_ENV = "production"
```

Simbolo activo:

```text
EURUSD
min_timeframe = M3
```

Parametros base del simbolo `EURUSD`:

```text
n1 = 2
n2 = 150
n3 = 4
size_pct = 0.02
```

Parametros base de la estrategia `PivotZoneTest`:

```text
tf_entry = M3
tf_zone  = M9
tf_stop  = M3
n1 = 3
n2 = 100
n3 = 5
size_pct = 0.05
timeframes = [M3, M9]
```

Importante: los parametros efectivos para `EURUSD` no son los de la estrategia base, sino los overrides del simbolo cuando existen. Para `EURUSD`, la estrategia acaba usando:

```text
n1 = 2
n2 = 150
n3 = 4
size_pct = 0.02
```

Esto afecta directamente a:

- separacion minima entre zonas;
- ancho de zona;
- cantidad minima de pivotes;
- riesgo base por operacion.

### 1.4. Flujo de un ciclo `run_once()`

Cada ciclo operativo hace lo siguiente:

1. Calcula `current_time`.
2. Sincroniza posiciones abiertas con el broker mediante `OrderExecutor.sync_state()`.
3. Actualiza `trade_history`: consulta cierres incrementales, persiste nuevos trades en el ledger y confirma el cursor MT5 al final.
4. Construye el snapshot de riesgo: cierres historicos desde MT5 mas PnL flotante abierto.
5. Aplica riesgo global.
6. Recorre cada simbolo configurado.
7. Aplica riesgo por simbolo.
8. Calcula timeframes requeridos por las estrategias que operan ese simbolo.
9. Pide datos al `MarketDataService`.
10. En development, simula fills SL/TP usando `FakeBroker.process_price_tick()`.
11. Recorre estrategias.
12. Aplica riesgo por estrategia.
13. Llama `strategy.generate_signals(data_by_timeframe)`.
14. Para senales BUY/SELL:
    - evita doble posicion por `symbol + magic_number`;
    - valida margen;
    - crea `OrderRequest`;
    - llama `OrderExecutor.execute_order()`.
15. Para senales CLOSE:
    - verifica que exista posicion;
    - crea orden de cierre;
    - llama `OrderExecutor.execute_order()`.
16. Llama al callback del visualizador si esta activo.

### 1.5. Salidas runtime

El bot usa principalmente estas salidas:

```text
last_trading_bot_v2.0_pivot_zone_syncro/logs/development.log
last_trading_bot_v2.0_pivot_zone_syncro/logs/production.log
last_trading_bot_v2.0_pivot_zone_syncro/logs/pivot_zones.log
last_trading_bot_v2.0_pivot_zone_syncro/plots/bot_events.jsonl
last_trading_bot_v2.0_pivot_zone_syncro/plots/closed_trades_cursor.json
last_trading_bot_v2.0_pivot_zone_syncro/plots/closed_trades_ledger.jsonl
last_trading_bot_v2.0_pivot_zone_syncro/plots/visualizer{SYMBOL}.html
```

`_clean_plots()` borra HTMLs previos y reinicia `plots/bot_events.jsonl`, pero conserva `plots/closed_trades_cursor.json` y `plots/closed_trades_ledger.jsonl`.

Responsabilidades de esas salidas:

- `plots/bot_events.jsonl`: eventos de la sesion actual para visualizacion y auditoria inmediata. Se reinicia al arrancar.
- `plots/closed_trades_cursor.json`: posicion incremental de lectura en MT5. Responde "hasta que deal se confirmo". No participa en el DD de produccion.
- `plots/closed_trades_ledger.jsonl`: historico persistente de trades cerrados aceptados por el bot. Alimenta eventos, visualizacion, auditoria y compatibilidad con modos sin snapshot historico. No es la fuente de verdad del DD de produccion.
- `plots/visualizer{SYMBOL}.html`: salida regenerable del visualizador.

---

## 2. Production

### 2.1. Perfil production

Production esta definido en `config.py` con:

```text
mode = production
broker.use_real_broker = True
broker.load_env_credentials = True
data.data_mode = production
logging.level = INFO
logging.log_file_path = logs/production.log
loop.timeframe_minutes = 3
loop.wait_after_close = 2
loop.skip_sleep_when_simulated = False
data.bootstrap_lookback_days_zone = 30
```

### 2.2. Arranque production paso a paso

1. `main()` llama `validate_config(settings)`.
2. `_configure_logging()` activa logs en `logs/production.log` y `logs/pivot_zones.log`.
3. `_clean_plots()` limpia HTMLs y reinicia `plots/bot_events.jsonl`.
4. `_build_broker()` crea `MetaTrader5Client`.
5. `MetaTrader5Client.connect()` llama `mt5.initialize()` y valida terminal/cuenta.
6. `_build_market_data_service()` usa el broker como proveedor, y `MarketDataService` lo envuelve como `ProductionDataProvider`.
7. `_build_risk_manager()` crea `RiskManager`.
8. `_build_strategies()` crea `PivotZoneTestStrategy` con el broker real inyectado.
9. `_build_auto_visualizer()` crea `AutoVisualizerService`.
10. Se carga `plots/closed_trades_ledger.jsonl` como historial inicial para eventos, visualizacion y compatibilidad local.
11. Se construye `TradingBot`.
12. Como el broker es real, `main()` llama `TradingBot.sync_clock_with_broker()`.
13. Si la sincronizacion de reloj falla, el arranque se aborta.
14. Si pasa, entra en `TradingBot.run_synchronized()`.

### 2.3. Sincronizacion de reloj en production

`TradingBot.sync_clock_with_broker()`:

- lee varias muestras de `broker_client.get_server_time()`;
- calcula offset con mediana;
- valida un residual final;
- aplica `clock_offset` si el residual esta dentro de umbral.

`MetaTrader5Client.get_server_time()`:

- consulta una cesta de simbolos de referencia;
- usa ticks frescos;
- prioriza el tick mas reciente;
- si no hay tick fresco, cae a reloj local UTC con warning.

Esto es critico porque `run_synchronized()` calcula los cierres de vela contra `_now()`, y `_now()` usa `datetime.now(UTC) + clock_offset`.

### 2.4. Datos en production

`ProductionDataProvider.get_data()`:

- recibe `symbol`, timeframes requeridos y `now`;
- calcula una ventana desde `now - max_lookback`;
- descarga el timeframe base del simbolo, actualmente `M3`;
- conserva un cache bruto acumulativo por simbolo;
- en ciclos posteriores descarga incremental desde la ultima vela cacheada;
- concatena y deduplica por indice;
- antes de entregar datos a la estrategia, aplica `_drop_open_base_bar()` al timeframe base;
- una vela base solo se considera cerrada si `timestamp + duracion_timeframe <= now`;
- devuelve `M3` ya filtrado a velas cerradas;
- resamplea `M9` desde ese `M3` cerrado si se requiere.

El resample usa:

```text
label = right
closed = right
drop_last_partial = True
```

Esto significa que las velas agregadas de `M9` quedan etiquetadas en su cierre y se descarta la ultima vela parcial.

Comportamiento actualizado: production ya no confia solo en el scheduler ni en que MT5 devuelva exclusivamente velas cerradas. Aunque `copy_rates_range()` incluya una vela `M3` recien abierta, `ProductionDataProvider` la mantiene en el cache bruto pero no la entrega a la estrategia hasta que su hora de cierre haya llegado. Los timeframes superiores se construyen desde esa misma base cerrada.

### 2.5. Ordenes en production

`OrderExecutor.execute_order()` es comun a ambos modos:

1. emite `order_submit`;
2. llama `broker_client.send_market_order(order_request)`;
3. si hay exito, emite `order_fill`;
4. registra posicion local;
5. emite evento `position`.

En production, el broker concreto es `MetaTrader5Client`.

`MetaTrader5Client.send_market_order()`:

- valida tipo de orden: `BUY`, `SELL`, `CLOSE`;
- valida volumen contra min/max/step del simbolo;
- obtiene tick actual;
- usa `ask` para BUY y `bid` para SELL;
- detecta filling mode compatible;
- normaliza SL/TP para evitar rechazos por stops demasiado cercanos;
- llama `mt5.order_send()`;
- devuelve `OrderResult` con `fill_price`.

### 2.6. Cierres y trades cerrados en production

Production no simula fills. Los cierres reales dependen de MT5.

El bot reconstruye trades cerrados mediante:

```text
MetaTrader5Client.get_closed_trades()
```

Este metodo:

- usa cursor persistente en `plots/closed_trades_cursor.json`;
- consulta deals en MT5;
- filtra entradas y salidas;
- reconstruye `TradeRecord`;
- deduplica localmente los deals de la consulta;
- deja preparado un cursor pendiente, pero no lo persiste todavia.

`TradingBot._update_trade_history()` incorpora esos `TradeRecord` a `trade_history`, escribe los cierres nuevos en `plots/closed_trades_ledger.jsonl`, emite eventos sinteticos de cierre cuando el broker no ofrece eventos nativos y solo entonces llama `commit_closed_trades_cursor()`.

Este flujo evita el caso peligroso:

```text
cursor avanzado, pero trade no persistido
```

Al arrancar, `TradingBot` reconstruye `trade_history` desde `plots/closed_trades_ledger.jsonl`, deduplica por clave estable y ordena cronologicamente para conservar continuidad local. En produccion, el calculo de drawdown no usa ese ledger como fuente de verdad: cada ciclo lee de MT5 una foto de cierres historicos y la combina con el PnL flotante abierto.

El flujo de DD en produccion es independiente del cursor:

1. `TradingBot._build_risk_snapshot()` lee `get_open_positions()` y guarda el `profit` flotante actual de cada posicion.
2. Si el broker expone `get_risk_closed_trades_snapshot()`, lo usa para descargar cierres historicos desde MT5.
3. `MetaTrader5Client` descubre el primer deal de trading disponible en MT5 mediante busqueda por tramos, cachea esa fecha solo en memoria y no escribe ningun archivo local para ese punto de inicio.
4. `RiskManager` calcula el maximo drawdown desde `risk.initial_balance`, acumulando PnL cerrado en orden cronologico y sumando el PnL flotante como ultimo punto de equity.
5. Si falla el snapshot de riesgo, el ciclo bloquea entradas nuevas para no operar con DD desconocido.

### 2.7. Visualizacion en production

`AutoVisualizerService` se activa por defecto.

En production puede tener `closed_trades_provider`, porque `MetaTrader5Client` expone `get_closed_trades_snapshot()`. Si `visualizer_start_from_end=False`, el visualizador puede hacer bootstrap historico:

- lee pivotes historicos;
- lee senales historicas;
- obtiene snapshot de trades cerrados MT5;
- genera eventos bootstrap para entradas/cierres historicos;
- renderiza `plots/visualizerEURUSD.html`.

### 2.8. Riesgos especificos de production

1. Las credenciales MT5 se cargan en `config.py`, pero `MetaTrader5Client.connect()` llama `mt5.initialize()` sin pasar explicitamente `server/login/password`. Si la terminal no esta previamente logueada, estas credenciales cargadas podrian no usarse.

2. El broker real usa reglas de mercado no replicadas al 100% por development:
   - spread bid/ask;
   - slippage;
   - stops level;
   - filling mode;
   - margen real;
   - rechazos de orden;
   - latencia;
   - ejecucion exacta de SL/TP.

3. La estrategia desactiva brackets pendientes opuestos en `MetaTrader5Client` para evitar sobre-apertura en cuentas hedge. Es correcto por seguridad, pero no es identico a development.

4. El filtro de drawdown por estrategia normaliza sufijos de timeframe en comentarios MT5. Por ejemplo, `PivotZoneTest-M3` empareja con el limite configurado como `PivotZoneTest`.

---

## 3. Development

### 3.1. Perfil development

Development esta definido con:

```text
mode = development
broker.use_real_broker = False
broker.load_env_credentials = False
data.data_mode = development
logging.level = DEBUG
logging.log_file_path = logs/development.log
loop.timeframe_minutes = 3
loop.wait_after_close = 0
loop.skip_sleep_when_simulated = True
data.bootstrap_lookback_days_zone = 0
```

### 3.2. Replay runner

`bot_trading/replay_runner.py` fuerza:

```python
config.ACTIVE_ENV = "development"
config.settings = config.load_settings("development")
```

Despues importa `bot_trading.main` y llama `main()`.

Esto significa que el replay no tiene un motor separado. Usa el mismo `main()`, el mismo `TradingBot`, la misma estrategia, el mismo `OrderExecutor`, el mismo `RiskManager` y el mismo visualizador.

La diferencia practica es que el loop sincronizado detecta reloj simulado CSV y no duerme.

### 3.3. Broker en development

Development usa `FakeBroker`, definido en `bot_trading/main.py`.

`FakeBroker` mantiene en memoria:

```text
orders_sent
open_positions
closed_trades
pending_orders
closed_position_events
pending_market_orders
filled_market_orders
pending_close_positions
_last_price
_symbol_info
```

Funciones clave:

- `send_market_order()`: simula apertura/cierre de posiciones.
- `process_price_tick()`: evalua OHLC de la vela actual para detectar SL/TP.
- `get_open_positions()`: devuelve posiciones abiertas simuladas.
- `get_closed_trades()`: devuelve trades cerrados simulados.
- `get_account_info()`: devuelve balance/equity fijo de 20000.
- `_get_symbol_info()`: usa `shared/instrument_specs.json` y defaults.
- `consume_closed_position_events()`: permite al motor emitir eventos sinteticos al cerrar por SL/TP.

### 3.4. Datos en development

Development usa `DevelopmentCsvDataProvider`.

Flujo:

1. Busca CSV por simbolo en `data_development`.
2. Acepta nombres exactos, nombres limpios sin `OANDA_`, variantes con coma o wildcard.
3. Requiere columnas `open`, `high`, `low`, `close`.
4. Acepta `volume`.
5. Requiere `time` epoch segundos/ms o `datetime`.
6. Normaliza indice temporal a UTC.
7. Ordena por fecha y elimina duplicados.
8. Inicializa cursor segun lookback.
9. En cada `get_data()` devuelve el slice hasta el cursor.
10. Resamplea timeframes superiores con `drop_last_partial=True`.
11. Avanza el cursor una vela base.
12. Lanza `StopIteration` al agotar datos.

Con el perfil actual, `bootstrap_lookback_days_zone=0`, development arranca desde el principio operativo del CSV y construye las zonas vela a vela. Esto es intencionado para comparar contra backtest cuando `backtest/data01` y `data_development` contienen el mismo OHLCV.

### 3.5. Reloj en development

`DevelopmentCsvDataProvider.get_simulated_now()` devuelve el timestamp de la ultima vela emitida.

`TradingBot.run_synchronized()` detecta ese reloj simulado y, si `skip_sleep_when_simulated=True`, ejecuta:

```text
simulated_now -> execution_time -> run_once(now=execution_time)
```

sin `time.sleep()`.

Esto hace que development sea determinista, rapido y adecuado para pruebas fuera de mercado.

### 3.6. Fills y cierres en development

Al obtener datos, `TradingBot.run_once()` detecta si el provider es `DevelopmentCsvDataProvider`. Si lo es:

1. toma la ultima vela del timeframe base;
2. extrae `open`, `high`, `low`, `close`;
3. llama `FakeBroker.process_price_tick()`;
4. procesa fills pendientes;
5. consume eventos de cierre;
6. emite eventos `order_fill` y `position` sinteticos para el visualizador.

`FakeBroker.process_price_tick()`:

- usa high/low para detectar toques intrabar;
- usa open si el nivel ya esta cruzado al abrir vela;
- respeta una vela de warmup para no cerrar inmediatamente en la misma vela de entrada;
- cierra por TP o SL;
- si TP y SL se tocan en la misma vela, prioriza SL y puede crear una posicion inversa simulada para alinear cierto comportamiento observado en backtest.

Esto permite ver trades, posiciones, logs y plots sin broker real, pero no reproduce al 100% la microestructura de MT5.

### 3.7. Visualizacion en development

El visualizador se activa igual que en production, salvo que su input de velas y eventos viene de CSV/FakeBroker.

`AutoVisualizerService.on_market_data()`:

- recibe velas M3 desde el callback del motor;
- acumula velas en `VisualizerStateStore`;
- lee nuevas lineas de `logs/pivot_zones.log`;
- lee nuevas lineas de `plots/bot_events.jsonl`;
- renderiza HTML si toca por `refresh_seconds`.

Eventos usados por plot:

```text
signal
order_submit
order_fill
position
pivot_confirmed
zone_saved
```

`BokehPlotBuilder` usa el `Plot` del backtest (`backtest bot v7.0 syncro/plotting.py`) de forma dinamica. Esto ayuda a mantener una visualizacion familiar entre backtest y live/replay.

### 3.8. Development como test fuera de mercado

Development ya sirve como test funcional fuera de mercado para:

- flujo completo del motor;
- lectura de datos;
- resample M3/M9;
- generacion de zonas;
- generacion de senales;
- calculo de SL/TP;
- calculo de lotaje;
- ejecucion simulada;
- eventos JSONL;
- logs;
- visualizador;
- agotamiento de datos.

Pero no debe interpretarse como replica exacta del resultado economico de production mientras existan estas diferencias operativas:

- modo de arranque distinto: replay completo del CSV en development frente a warmup historico en production;
- ejecucion SL/TP simulada con OHLC;
- sin spread bid/ask real;
- sin slippage real;
- sin rechazos reales de MT5;
- sin margen real dinamico;
- sin tiempo/latencia real;
- diferente tratamiento de brackets.

---

## 4. Sincronizacion de funciones entre Production y Development

### 4.1. Objetivo correcto de sincronizacion

Development deberia ser usado como test fuera de mercado de production. Para eso, el objetivo no deberia ser "mismo PnL exacto", sino esta jerarquia:

```text
Nivel 1 - Paridad fuerte:
  mismas zonas, mismas senales, mismo SL, mismo TP, mismo size

Nivel 2 - Paridad funcional:
  mismos eventos principales, mismo plot, mismos logs de decision

Nivel 3 - Paridad aproximada:
  cierres y PnL parecidos, sabiendo que MT5 real puede ejecutar distinto
```

La paridad fuerte deberia compararse antes de la ejecucion real de mercado. El PnL de production siempre puede diferir por condiciones de broker.

### 4.2. Codigo compartido

Production y development comparten:

| Area | Codigo compartido | Impacto |
|---|---|---|
| Config base | `DEFAULT_SYMBOLS`, `DEFAULT_STRATEGIES` | Misma declaracion de simbolos y estrategia |
| Validacion | `validate_config()` | Evita combinaciones incoherentes broker/datos |
| Motor | `TradingBot` | Mismo ciclo operativo |
| Registro | `StrategyRegistry` | Mismos magic numbers |
| Riesgo | `RiskManager` | Mismos limites logicos |
| Estrategia | `PivotZoneTestStrategy` | Misma decision de zonas/senales |
| Senales | `Signal`, `SignalType` | Mismo contrato estrategia -> motor |
| Ordenes | `OrderRequest`, `OrderResult`, `OrderExecutor` | Misma ruta de conversion senal -> orden |
| Eventos | `EventLogger` | Mismo formato JSONL |
| Plot | `AutoVisualizerService`, `EventReader`, `VisualizerStateStore`, `BokehPlotBuilder` | Mismo pipeline de visualizacion |
| Specs | `shared/instrument_specs.json` | Fallback comun de tick/volumen/margen |

### 4.3. Puntos donde se bifurca el flujo

| Punto | Production | Development | Afecta resultado |
|---|---|---|---|
| Broker | `MetaTrader5Client` | `FakeBroker` | Si |
| Datos | MT5 `copy_rates_range()` | CSV local | Si |
| Reloj | broker/local con offset | timestamp CSV | Si |
| Sleep | espera real | sin sleep | No deberia afectar senales, salvo timing |
| Lookback | 30 dias de warmup historico | 0 dias para replay desde inicio del CSV | Si se compara desde el arranque; es intencionado |
| Fills | MT5 real | OHLC simulado | Si, mucho |
| SL/TP | nativo en posicion MT5 | brackets/fills simulados | Si |
| AccountInfo | cuenta real | fijo 20000 | Si, afecta size |
| SymbolInfo | MT5 + fallback specs | specs + defaults | Si, afecta size |
| Trades cerrados | DD con snapshot MT5 directo; ledger + cursor para eventos/dedupe | ledger persistente + memoria FakeBroker | Si |
| Visualizer bootstrap | puede usar snapshot MT5 | lee JSONL/FakeBroker | Afecta visualizacion historica |

### 4.4. Divergencias prioritarias

#### 4.4.1. Lookback inicial

Production:

```text
bootstrap_lookback_days_zone = 30
```

Development:

```text
bootstrap_lookback_days_zone = 0
```

Esta diferencia no es un fallo de configuracion; responde a dos objetivos distintos:

- `development=0` permite reproducir el dataset completo desde la primera vela y validar paridad contra el backtest cuando ambos usan el mismo OHLCV.
- `production=30` permite que el bot real no arranque sin memoria de zonas; carga historia pasada desde MT5 y despues evalua las velas nuevas en tiempo real.

La estrategia es incremental y construye memoria de zonas. Por eso, si se comparan development y production desde sus arranques naturales, las zonas iniciales no tienen por que coincidir: development esta replayando desde el origen del CSV y production esta arrancando en una fecha viva con 30 dias previos de warmup.

Conclusion: la configuracion actual es correcta para sus dos usos. Development valida backtest desde el inicio del dataset; production arranca caliente para operar. Solo para una prueba de paridad operacional production-like debe fijarse una fecha T, cargar los 30 dias anteriores como warmup y comparar las senales desde T.

#### 4.4.2. Fills intrabar

Development decide cierres usando OHLC de la vela. Production ejecuta en MT5 con bid/ask y reglas de broker. Si una vela toca SL y TP, development aplica una regla interna, pero production dependera del orden real de ticks.

Conclusion: development puede validar comportamiento funcional de cierre, pero no el orden exacto de fills reales.

#### 4.4.3. SL/TP nativo vs brackets pendientes

La estrategia contiene `_use_pending_brackets()`.

- En `FakeBroker`, permite brackets pendientes simulados.
- En `MetaTrader5Client`, los desactiva para evitar que una cuenta hedge abra una posicion contraria.
- El stop dinamico una sola vez reutiliza este mismo flujo: en `FakeBroker` modifica/recrea el bracket de SL y en `MetaTrader5Client` actualiza el SL nativo de la posicion con `TRADE_ACTION_SLTP`.

Conclusion: esta divergencia es intencionada y razonable por seguridad, pero debe documentarse como limite de paridad.

#### 4.4.4. Politica de vela base cerrada en production

Production aplica una politica explicita sobre el timeframe base antes de llamar a la estrategia.

`ProductionDataProvider.get_data()` mantiene un cache bruto acumulativo, pero entrega a `data_by_timeframe` una version filtrada mediante `_drop_open_base_bar()`:

```text
vela_cerrada = timestamp + duracion_timeframe <= now
```

Con la configuracion actual, una vela `M3` abierta a `00:03` no se entrega en `00:03:02`; pasa a estar disponible desde `00:06:00`.

Conclusion: el riesgo de que production evalue una vela `M3` recien abierta queda mitigado en el proveedor de datos. La estrategia sigue consumiendo toda la serie recibida, pero esa serie ya representa velas base cerradas. `M9` tambien se resamplea desde esa base filtrada, por lo que no hereda datos de una `M3` abierta.

#### 4.4.5. Sizing y margen

La estrategia calcula size con:

```text
risk_fraction = size_pct * 0.1
```

Para `EURUSD`, `size_pct=0.02`, asi que el riesgo base efectivo es:

```text
0.02 * 0.1 = 0.002 = 0.2% del equity
```

Luego se modula entre `0.8` y `1.2` segun distancia al stop.

Production usa equity y symbol info reales. Development usa equity fijo y specs estaticas.

Conclusion: incluso con misma senal, el lotaje puede diferir si la cuenta real no coincide con los datos simulados.

### 4.5. Recomendaciones de sincronizacion

1. Mantener el perfil `development` con `bootstrap_lookback_days_zone=0` cuando el objetivo sea comparar contra backtest desde el inicio del CSV.

2. Para comparar contra un arranque production-like, crear un escenario de paridad operacional con una fecha T: el CSV debe incluir al menos 30 dias previos para warmup y la comparacion debe empezar despues de ese warmup.

3. Definir el criterio oficial de paridad segun el objetivo:

```text
Backtest vs development:
  mismo CSV completo, replay desde inicio, comparar zonas/senales/SL/TP/size.

Production-like:
  misma fecha T, mismo warmup previo, comparar desde T.
```

4. Anadir un test de paridad con dataset fijo:

```text
mismo CSV
mismo simbolo
mismas specs
misma fecha de comparacion
misma ventana de warmup cuando aplique
comparar zonas/senal/sl/tp/size/eventos
```

5. Mantener tests de regresion para la politica de vela base cerrada en production: `test_production_base_timeframe_drops_open_m3_candle`, `test_production_base_timeframe_keeps_m3_after_close` y `test_production_resamples_higher_timeframe_from_closed_base_only`.

6. Documentar que production usa SL/TP nativo y development usa simulacion OHLC/brackets.

7. Normalizar `strategy_name` de trades cerrados para que `RiskManager.check_strategy_risk_limits()` no falle si MT5 devuelve comentario `PivotZoneTest-M3` en vez de `PivotZoneTest`.

8. Revisar el uso de credenciales MT5: `config.py` carga variables, pero `MetaTrader5Client.connect()` no las pasa explicitamente a `mt5.initialize()`.

9. Corregir comentarios de `DEFAULT_SYMBOLS`, porque algunos no coinciden con el valor real (`n1=2` comentado como 3 anchos, `n2=150` comentado como 100/100). No afecta ejecucion, pero afecta auditoria humana.

---

## 5. Comparacion y desarrollo de la estrategia de trading entre Production y Development

### 5.1. Estrategia comun

Ambos entornos usan `PivotZoneTestStrategy`.

La estrategia opera con tres timeframes conceptuales:

```text
TF_entry = M3
TF_zone  = M9
TF_stop  = M3
```

En la configuracion actual, `M9` se obtiene por resample desde `M3`.

### 5.2. Flujo interno de `PivotZoneTestStrategy.generate_signals()`

1. Valida que existan los timeframes requeridos.
2. Obtiene el simbolo desde `df.attrs["symbol"]`.
3. Verifica `allowed_symbols`.
4. Resuelve parametros efectivos por simbolo.
5. Toma `df_entry`, `df_zone`, `df_stop`.
6. Actualiza estado por simbolo.
7. Procesa zonas pivote en `TF_zone`.
8. Procesa pivotes de stop en `TF_stop`.
9. Consulta posicion abierta en broker por simbolo y magic number.
10. Si hay posicion:
    - sincroniza estado interno;
    - recupera SL/TP/direccion;
    - gestiona o limpia brackets;
    - evalua el stop dinamico una sola vez con el ultimo pivote confirmado de `TF_stop`;
    - no busca nueva entrada.
11. Si no hay posicion:
    - busca breakout;
    - selecciona zona objetivo;
    - calcula entry, SL, TP;
    - valida coherencia;
    - calcula lotaje;
    - emite evento `signal`;
    - devuelve `Signal(BUY/SELL)`;
    - congela estado interno esperando ejecucion.

### 5.3. Construccion de zonas pivote

La estrategia usa pivotes confirmados de tres velas.

El detector no usa look-ahead operativo. Cuando llega una vela nueva, evalua el patron de las tres velas previas y confirma la vela central.

Pivote maximo:

```text
high[i-3] < high[i-2] > high[i-1]
```

Pivote minimo:

```text
low[i-3] > low[i-2] < low[i-1]
```

La zona se construye asi:

1. Aparece un pivote.
2. Si no hay proyecto de zona, inicia proyecto.
3. Si hay proyecto y el pivote cae dentro del ancho permitido, se agrega.
4. Si cae fuera, reinicia el proyecto.
5. El ancho se calcula con:

```text
width = ATR(14) * (n2 / 100)
```

6. Si no hay ATR valido, usa:

```text
width = abs(close) * 0.001
```

7. La zona se bloquea si:

```text
pivots >= n3
has_been_above = True
has_been_below = True
```

8. La zona bloqueada se guarda si no esta demasiado cerca de una zona previa.

Distancia minima:

```text
min_distance = new_width * n1
```

Para `EURUSD` actual:

```text
n1 = 2
n2 = 150
n3 = 4
```

### 5.4. Breakout de entrada

La entrada requiere una ruptura confirmada:

1. Deben existir zonas guardadas.
2. Debe haber al menos 5 velas en `TF_entry`.
3. Al menos 2 de las 3 velas previas deben cerrar dentro de la zona.
4. Para LONG:

```text
close[-2] > top
close[-1] > top
```

5. Para SHORT:

```text
close[-2] < bot
close[-1] < bot
```

6. Debe existir una zona objetivo en direccion del trade.

La estrategia descarta rupturas sin origen claro dentro de la zona o sin objetivo disponible.

### 5.5. Stop loss

El stop inicial es estructural.

Para LONG:

```text
ultimo pivot_min confirmado en TF_stop dentro de la zona rota
```

Para SHORT:

```text
ultimo pivot_max confirmado en TF_stop dentro de la zona rota
```

Si no existe ese pivote dentro de la zona rota, la entrada se descarta.

Despues de abrirse la posicion existe una unica actualizacion dinamica del SL. No es trailing continuo: es un break-even estructural por pivote, una sola vez.

Para LONG:

```text
primer pivot_min confirmado en TF_stop posterior a la apertura y por encima del entry
```

Para SHORT:

```text
primer pivot_max confirmado en TF_stop posterior a la apertura y por debajo del entry
```

Cuando se ejecuta esta actualizacion, el SL no vuelve a moverse durante esa operacion.

### 5.6. Take profit

El TP se basa en la zona objetivo mas cercana en direccion del trade.

Para LONG:

```text
buscar zona con midpoint superior al midpoint de la zona rota
```

Para SHORT:

```text
buscar zona con midpoint inferior al midpoint de la zona rota
```

El precio final de TP es el borde de la zona objetivo mas cercano al entry.

### 5.7. Lotaje

El size se calcula por riesgo hasta el stop.

Formula conceptual:

```text
risk_fraction_base = size_pct * 0.1
modulation = clamp(sqrt(0.01 / stop_distance_pct), 0.8, 1.2)
risk_budget = equity * risk_fraction_base * modulation
ticks_to_stop = abs(entry - stop) / tick_size
loss_per_lot = ticks_to_stop * tick_value
raw_lots = risk_budget / loss_per_lot
```

Luego se ajusta por:

- `volume_min`;
- `volume_step`;
- `volume_max`;
- `margin_per_lot` o `margin_initial`;
- `margin_free`.

Para el `EURUSD` actual:

```text
size_pct = 0.02
risk_fraction_base = 0.002
riesgo base = 0.2% del equity
```

### 5.8. Gestion durante posicion abierta

Si hay posicion abierta:

- no busca nueva entrada;
- sincroniza estado local con broker;
- recupera direccion, entry, SL y TP;
- en FakeBroker puede crear/recuperar brackets pendientes;
- en MT5 real cancela pendientes opuestas por seguridad;
- puede actualizar el SL una sola vez con break-even estructural por pivote;
- puede reanclar TP si aparece una zona intermedia mejor.

Stop dinamico una sola vez:

- no es trailing continuo;
- requiere un nuevo pivote confirmado en `TF_stop` posterior a la apertura;
- en LONG usa el primer `pivot_min` por encima del entry;
- en SHORT usa el primer `pivot_max` por debajo del entry;
- en FakeBroker actualiza la pendiente/posicion simulada;
- en MT5 modifica el SL nativo de la posicion con `TRADE_ACTION_SLTP`.

TP adaptativo:

- solo actua si `adaptive_tp=True`;
- requiere nueva zona a favor del trade;
- la nueva zona debe estar entre precio actual y TP anterior;
- la mejora minima es `adaptive_tp_min_improvement_pct = 0.25`;
- en FakeBroker recrea pendiente TP;
- en MT5 intenta modificar SL/TP de la posicion si aplica.

### 5.9. Codigo compartido que protege la paridad

| Componente | Motivo de paridad |
|---|---|
| `PivotZoneTestStrategy` | Misma logica de zonas y senales |
| `_Pivot3CandleState` | Mismo retardo de confirmacion de pivotes |
| `_resample()` | Misma semantica M3 -> M9 cuando se usa provider compartido |
| `StrategyRegistry` | Mismo magic number |
| `OrderExecutor` | Mismo formato de eventos y ordenes |
| `EventLogger` | Mismo JSONL |
| `BokehPlotBuilder` | Misma representacion visual |
| `RiskManager` | Mismo bloqueo por drawdown/margen logico |

### 5.10. Diferencias que afectan el resultado de la estrategia

| Diferencia | Efecto probable |
|---|---|
| `bootstrap_lookback_days_zone`: production 30, development 0 | Arranques con objetivo distinto: warmup real vs replay completo del CSV |
| CSV vs MT5 OHLCV | Velas distintas por fuente, timezone, gaps, precision |
| Politica de vela base cerrada en production | Mitiga senales adelantadas por velas M3 abiertas; depende de que `now` este sincronizado con broker |
| Equity real vs equity fijo 20000 | Size diferente |
| SymbolInfo real vs specs estaticas | Size y validacion de volumen diferentes |
| SL/TP real MT5 vs OHLC simulado | Cierres y PnL diferentes; el stop dinamico se actualiza en ambos, pero el fill sigue dependiendo del motor real o simulado |
| Spread/slippage/stops level | Ordenes production pueden llenar/rechazar distinto |
| Ledger/cursor de closed trades | Historial de riesgo production depende del ledger; el cursor solo marca el ultimo deal confirmado |
| Comentario de estrategia en trades MT5 | Riesgo por estrategia podria filtrar distinto |

### 5.11. Conclusion estrategica

La estrategia esta razonablemente sincronizada en la parte de decision: zonas, breakout, SL inicial, break-even estructural por pivote una sola vez, TP y size salen del mismo codigo.

La parte no sincronizada es la ejecucion:

- development simula con OHLC;
- production ejecuta en MT5 real.

Por tanto, development debe ser usado principalmente para validar:

- que la estrategia detecta las mismas zonas;
- que emite las mismas senales;
- que el plot refleja lo esperado;
- que los eventos y logs son coherentes;
- que el flujo completo no rompe fuera de mercado.

No debe usarse como garantia de mismo fill, mismo PnL o mismo orden exacto de salida en velas donde SL/TP puedan tocarse intrabar.

---

## 6. PLANIFICADOR - plan recomendado para usar Development como test real de Production

1. Crear una configuracion o escenario de paridad operacional solo cuando se quiera comparar contra un arranque production-like.

   Objetivo: misma fecha T, mismo warmup previo, mismos parametros, mismo simbolo, mismo initial balance y mismas specs.

2. Generar o descargar CSV production-like.

   Objetivo: que development use datos M3 equivalentes a los que MT5 entrega, con suficiente historial previo.

3. Ejecutar `python -m bot_trading.replay_runner`.

   Objetivo: producir `logs/development.log`, `logs/pivot_zones.log`, `plots/bot_events.jsonl` y HTMLs.

4. Comparar decision previa a broker.

   Comparar:

```text
zone_saved
signal
side
entry reference
SL
TP
size
bar_index
ts_event
```

5. Comparar visualizacion.

   Revisar:

```text
zonas dibujadas
senales
fills simulados
posiciones
lineas de trade
outliers filtrados
```

6. Separar divergencias intencionadas.

   Etiquetar como no-paridad aceptada:

```text
fills reales MT5
spread
slippage
rechazos
margen real
orden exacto intrabar
```

7. Crear tests de paridad.

   Un test minimo deberia fijar un dataset y verificar que la estrategia emite la misma senal bajo condiciones controladas.

---

## 7. DOCUMENTADOR - resumen final

El bot ya tiene una arquitectura adecuada para que development sea un laboratorio fuera de mercado de production. La mayor parte del codigo critico es compartido:

- motor;
- estrategia;
- riesgo;
- senales;
- ordenes;
- eventos;
- visualizador.

Las diferencias actuales que mas afectan a resultados son:

1. arranque production con 30 dias de warmup vs development con replay desde inicio del CSV;
2. fills reales MT5 vs fills OHLC simulados;
3. SL/TP nativo en production vs brackets simulados en development, aunque la regla del stop dinamico una sola vez es comun;
4. dependencia de reloj sincronizado para decidir cuando una vela M3 ya esta cerrada;
5. equity/symbol info real vs valores fijos/specs;
6. estrategia reconstruida desde comentarios MT5 para riesgo por estrategia.

El siguiente paso recomendado no es reescribir la arquitectura, sino crear una capa de paridad operacional:

```text
development_parity
CSV suficiente
fecha T definida
warmup previo equivalente cuando aplique
test de zonas/senales
documentacion de divergencias de ejecucion
```

Con eso, development puede convertirse en una prueba fiable de funcionamiento de production para trades, comportamiento del plot, logs y decisiones de estrategia, dejando claro que el PnL final depende de condiciones reales de mercado y broker.
