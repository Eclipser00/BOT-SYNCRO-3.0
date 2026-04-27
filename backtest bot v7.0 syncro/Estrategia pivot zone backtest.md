# Informe - Estrategia Pivot Zone Backtest

## 1. Resumen ejecutivo

La estrategia activa del proyecto `backtest bot v7.0 syncro` es `PivotZoneTest`.

Es una estrategia de ruptura de zonas pivote con enfoque `zone-to-zone`: detecta zonas relevantes del precio, espera una ruptura confirmada, abre posicion en la direccion de la ruptura, coloca un stop estructural dentro de la zona rota y un take profit hacia la siguiente zona ya existente.

La configuracion actual no opera por medias, RSI o Bollinger. Esas estrategias existen en `strategies.py`, pero no estan activas en `config.py`.

Referencias principales:

- `config.py`: `STRATEGIES`
- `strategies.py`: clase `PivotZoneTest`
- `backtest.py`: motor de ejecucion y optimizacion

## 2. Estrategia activa

En `config.py`, la lista `STRATEGIES` contiene unicamente:

```python
PivotZoneTest
```

Por tanto, el backtest solo ejecuta esta estrategia. Las demas estrategias aparecen importadas o comentadas:

- `DosMedias`
- `Tres_Medias_Filtered`
- `RSI_WMA_TurnFilters`
- `SMA_sobre_RSI`
- `Bollinger_Bands`
- `Bollinger_Ratio`

Nota importante: el comentario de `config.py` indica "Multi-timeframe wrapper", pero el codigo activo usa `PivotZoneTest` directamente, no `make_multi_tf(PivotZoneTest)`. El comportamiento multi-timeframe se consigue principalmente desde el motor de backtest, que auto-resamplea el feed base cuando detecta `PivotZoneTest` con un solo feed.

## 3. Parametros activos de optimizacion

La estrategia optimiza tres parametros:

| Parametro | Uso real | Rango activo |
|---|---|---|
| `n1` | Multiplicador de distancia minima entre zonas guardadas | `2, 3` |
| `n2` | Ancho de zona como porcentaje del ATR | `150, 175, 200` |
| `n3` | Numero minimo de pivotes para validar zona | `4, 5, 6` |

Esto genera 18 combinaciones por activo:

```text
2 valores n1 x 3 valores n2 x 3 valores n3 = 18 combinaciones
```

La metrica principal de seleccion es:

```python
OPTIMIZE_MAXIMIZE = 'Profit Factor'
```

Es decir, el sistema elige la combinacion que maximiza la relacion entre ganancias brutas y perdidas brutas.

## 4. Timeframes de trabajo

La configuracion declara:

| Timeframe | Valor |
|---|---|
| Entrada | 3 minutos |
| Zona | 9 minutos |
| Stop | 3 minutos |

En la practica, si el backtest recibe un solo CSV base, el motor crea automaticamente el timeframe de zona mediante resample a `M9`.

El flujo habitual queda asi:

- `TF_entry`: feed base, por ejemplo M3.
- `TF_zone`: resample automatico a M9.
- `TF_stop`: si no hay tercer feed explicito, usa el mismo feed base que `TF_entry`.

Por tanto, con el estado actual del proyecto, el stop se calcula sobre el mismo timeframe de entrada.

## 5. Construccion de zonas pivote

La zona pivote se construye con el indicador `PivotZone`.

Una zona valida necesita dos condiciones principales:

1. Agrupacion de pivotes.
2. Cambio de rol.

### 5.1. Agrupacion de pivotes

El indicador busca pivotes confirmados mediante una estructura de 3 velas:

- Pivote maximo: la vela central tiene un maximo superior al de la vela anterior y posterior.
- Pivote minimo: la vela central tiene un minimo inferior al de la vela anterior y posterior.

Cuando aparecen varios pivotes cerca entre si, el indicador empieza a formar un proyecto de zona.

Para que ese proyecto pueda convertirse en zona valida, deben existir al menos `n3` pivotes agrupados dentro de un rango de precio determinado por el ancho de zona.

El ancho de zona se calcula asi:

```text
width = ATR(14) * (n2 / 100)
```

Por ejemplo, si `n2 = 200`, el ancho de la zona equivale a `2.0 * ATR(14)`.

### 5.2. Cambio de rol

El cambio de rol significa que el mercado ha reconocido esa misma zona desde los dos lados.

Para validar una zona, no basta con que haya varios pivotes cerca. Ademas, el precio debe haber cerrado claramente:

- por encima del borde superior de la zona;
- y por debajo del borde inferior de esa misma zona.

Esto demuestra que la zona no es solo una acumulacion casual de pivotes, sino un nivel que el precio ha tratado como area relevante desde ambos lados.

En terminos practicos:

```text
Si close > top:
    la zona ha sido superada por arriba.

Si close < bot:
    la zona ha sido superada por abajo.
```

Cuando ambas cosas han ocurrido en la misma zona, el indicador considera que existe cambio de rol.

La idea de trading detras de esto es que una zona valida debe poder comportarse como soporte y resistencia en distintos momentos. Es decir:

- antes pudo frenar al precio desde arriba;
- despues pudo frenar o ser atravesada desde abajo;
- o al reves.

Hasta que el precio no ha pasado claramente por ambos lados, la zona sigue siendo solo un proyecto interno y no se guarda como zona operable.

### 5.3. Bloqueo de zona

Cuando se cumplen las dos condiciones:

```text
pivotes agrupados >= n3
precio cerro por encima de la zona
precio cerro por debajo de la zona
```

la zona se bloquea.

Bloquear la zona significa que:

- su centro queda fijo;
- su ancho queda fijo;
- pasa a estado valido;
- puede ser guardada por `PivotZoneTest`;
- puede usarse despues para rupturas, objetivos y visualizacion.

### 5.4. Aclaracion sobre `n1`

Hay una confusion importante con `n1`, porque aparece en mas de un nivel del codigo.

En el indicador `PivotZone`, existe un parametro `n1`, pero realmente no se usa como periodo ATR dinamico. Dentro del indicador, el ATR esta fijado internamente a 14 mediante:

```text
self._atr_period = 14
```

Ademas, cuando `PivotZoneTest` crea el indicador `PivotZone`, le pasa:

```text
n1 = 14
n2 = self.p.n2
n3 = self.p.n3
```

Por tanto, en la estrategia activa, el `n1` optimizado no controla el ATR.

El `n1` optimizado de `PivotZoneTest` se usa despues para otra cosa: controlar la distancia minima entre zonas guardadas.

Cuando aparece una nueva zona valida, la estrategia calcula:

```text
min_distance = ancho_zona * n1
```

Si la nueva zona esta demasiado cerca de una zona ya guardada, se rechaza.

Asi que, en esta version:

| Parametro | Uso real |
|---|---|
| `n1` | Multiplicador de separacion minima entre zonas guardadas |
| `n2` | Ancho de zona como porcentaje del ATR(14) |
| `n3` | Numero minimo de pivotes necesarios para validar una zona |

Esta separacion evita que el sistema guarde muchas zonas casi pegadas entre si, reduciendo ruido y duplicados.

## 6. Guardado y filtro de zonas

Cuando una zona pasa de no valida a valida, la estrategia intenta guardarla en `_saved_zones`.

Antes de guardarla comprueba que no este demasiado cerca de otra zona ya existente. La distancia minima se calcula asi:

```text
min_distance = ancho_zona * n1
```

Si la nueva zona esta demasiado cerca de una zona anterior, se rechaza.

Las zonas aceptadas no se borran. Quedan disponibles para:

- detectar rupturas;
- seleccionar zona objetivo;
- dibujar niveles en el plot;
- recalcular take profit adaptativo.

## 7. Condiciones de entrada

La estrategia solo busca entradas si:

- no hay posicion abierta;
- no hay orden de entrada pendiente;
- existen zonas guardadas;
- hay suficiente historial;
- el precio viene desde dentro de una zona;
- existe una zona objetivo en la direccion del trade.

Para validar que el precio viene desde dentro, exige que al menos 2 de las ultimas 3 velas anteriores hayan cerrado dentro de la zona.

Entrada LONG:

```text
close[-1] > top
close[0]  > top
```

Entrada SHORT:

```text
close[-1] < bot
close[0]  < bot
```

Ademas, no entra si no existe una zona objetivo ya conocida en la direccion del trade. Esto evita tomar beneficios contra una zona futura que aun no existe en el historico en ese momento.

## 8. Take profit

El take profit se basa en la zona pivote objetivo mas cercana en la direccion del trade.

Para un LONG:

- busca una zona con midpoint por encima del midpoint de la zona rota.

Para un SHORT:

- busca una zona con midpoint por debajo del midpoint de la zona rota.

El precio de TP se coloca en el borde mas cercano de la zona objetivo respecto al precio de entrada.

La orden de take profit se envia como orden `Limit`.

## 9. Stop loss

El stop inicial es estructural, no porcentual fijo.

Para un LONG:

- usa el ultimo swing low confirmado en `TF_stop` que este dentro de la zona rota.

Para un SHORT:

- usa el ultimo swing high confirmado en `TF_stop` que este dentro de la zona rota.

Si no encuentra ese pivote dentro de la zona rota, no abre operacion.

El stop se coloca como orden `Stop`.

Despues de ejecutarse la entrada, la estrategia puede mover el stop una sola vez. No es trailing continuo: es un break-even estructural por pivote.

Para un LONG:

- usa el primer swing low confirmado en `TF_stop` posterior a la apertura que quede por encima del precio de entrada.

Para un SHORT:

- usa el primer swing high confirmado en `TF_stop` posterior a la apertura que quede por debajo del precio de entrada.

Cuando esta actualizacion se aplica, el stop no vuelve a moverse durante esa operacion.

## 10. Gestion de riesgo y tamano de posicion

El parametro `size_pct` de `PivotZoneTest` es `0.05`.

Pero no se usa directamente como 5% de riesgo. El codigo lo escala con:

```text
risk_fraction = size_pct * 0.1
```

Por tanto:

```text
0.05 * 0.1 = 0.005
```

Eso equivale aproximadamente a 0.5% de equity como riesgo base antes de la modulacion por distancia al stop.

Luego el sistema modula el riesgo segun la distancia del stop:

- minimo: `0.8`
- maximo: `1.2`
- referencia: stop al 1% del precio

La formula general calcula:

```text
riesgo monetario / perdida por lote hasta stop
```

Tambien usa las especificaciones del instrumento desde:

```text
../shared/instrument_specs.json
```

Para `EURUSD`, existen valores como:

- `trade_tick_size`
- `trade_tick_value`
- `volume_min`
- `volume_step`
- `volume_max`
- `margin_per_lot`

Si faltan `tick_size` o `tick_value`, el tamano resultante sera 0 y no habra entrada.

## 11. Broker, capital y costes

La configuracion activa es:

| Concepto | Valor |
|---|---|
| Capital inicial | `20000` |
| Apalancamiento | `1:5` |
| Comision | `0.0025%` |
| Ejecucion | `TRADE_ON_CLOSE = True` |

En `main.py`, la comision se convierte de porcentaje a fraccion dividiendo entre 100. Por ejemplo:

```text
0.0025% -> 0.000025
```

El margen de Backtrader se calcula como:

```text
margin = 1 / MARGIN
```

Con `MARGIN = 5`, el margen usado es `0.2`, equivalente a apalancamiento 1:5.

## 12. Gestion durante la operacion

Cuando se ejecuta la entrada, `notify_order` coloca automaticamente:

- stop loss;
- take profit;
- direccion del trade;
- precio de entrada;
- precio de TP activo.

Mientras la posicion esta abierta, si aparece el primer pivote valido de `TF_stop` que cruza el precio de entrada a favor del trade, reemplaza la orden `Stop` existente por una nueva orden `Stop`. Es una unica actualizacion estructural, no trailing continuo.

Si se ejecuta el stop:

- cancela el TP;
- limpia el estado interno del trade.

Si se ejecuta el TP:

- cancela el stop;
- limpia el estado interno del trade.

No hay piramidacion explicita. La estrategia no abre una nueva entrada si ya hay posicion o entrada pendiente.

## 13. Take profit adaptativo

La estrategia tiene `adaptive_tp = True`.

Si aparece una nueva zona mientras hay una posicion abierta, el sistema puede reanclar el TP si encuentra una zona objetivo mas cercana y suficientemente mejor.

La mejora minima requerida es:

```text
adaptive_tp_min_improvement_pct = 0.25
```

Esto significa que el nuevo TP debe mejorar al menos un 25% la distancia respecto al TP anterior.

## 14. Metricas y resultados

El backtest calcula metricas de:

- equity final;
- equity peak;
- retorno;
- buy and hold;
- retorno anualizado;
- volatilidad anualizada;
- Sharpe;
- Sortino;
- Calmar;
- drawdown maximo;
- drawdown promedio;
- numero de trades;
- win rate;
- best/worst trade;
- avg win;
- avg loss;
- profit factor;
- expectancy;
- SQN.

La metrica usada para elegir mejores parametros es `Profit Factor`.

## 15. Robustez

Actualmente estan desactivados:

```python
USE_CSCV = False
USE_STRESS = False
USE_WF = False
```

Por tanto, en la ejecucion normal no se lanzan:

- CSCV + PBO;
- stress test de costes;
- walk-forward.

El codigo para esos analisis existe, pero no se ejecuta con la configuracion actual.

## 16. Datos actuales detectados

En `data01` existe actualmente:

```text
EURUSD.csv
```

El CSV tiene formato compatible:

```text
time,open,high,low,close,Volume
```

La configuracion del descargador MT5 apunta a:

| Campo | Valor |
|---|---|
| Simbolo | `EURUSD` |
| Timeframe | `M3` |
| Inicio UTC | `2026-03-30 00:00:00` |
| Fin UTC | `2026-04-10 23:59:55` |

## 17. Conclusion

La estrategia activa `PivotZoneTest` es una estrategia estructural de ruptura de zonas pivote.

Su logica principal es:

1. Detectar zonas pivote validas en timeframe superior.
2. Guardarlas si no estan demasiado cerca de zonas anteriores.
3. Esperar que el precio venga desde dentro de una zona.
4. Confirmar ruptura con dos cierres consecutivos fuera de la zona.
5. Exigir una zona objetivo ya existente en la direccion del trade.
6. Calcular stop con pivote estructural dentro de la zona rota.
7. Dimensionar la posicion por riesgo hasta stop usando especificaciones reales del instrumento.
8. Colocar entrada, stop y take profit.
9. Si aparece el primer pivote valido de `TF_stop` que cruza el entry a favor, reemplazar el stop una sola vez.
10. Cerrar por stop o por TP.
11. Opcionalmente reanclar el TP si aparece una zona mejor durante el trade.

Es una estrategia bastante restrictiva: evita operar rupturas sin origen claro, sin stop estructural o sin objetivo definido. Esto reduce entradas impulsivas, pero tambien puede dejar muchas rupturas sin operar.
