# Momentum lookback costed scan - verdict

Fecha local: 2026-06-03

## Veredicto

```text
NO_EDGE_EJECUTABLE_CONFIRMADO
```

Si usamos precios proxy de Polymarket con tolerancia de entrada amplia, los lookbacks cortos mejoran mucho el momentum original. Pero cuando exigimos entrada casi inmediata o ask real del orderbook, la evidencia no queda robusta.

Esto sugiere una hipotesis interesante:

```text
El edge proxy podria venir de latencia / stale pricing / actualizacion lenta del mercado,
no necesariamente de una ventaja ejecutable al ask.
```

## Protocolo ejecutado

Script:

```text
scripts/scan_momentum_lookbacks_costed.py
```

Formula de senal:

```text
t_signal = ts_open - gap
momentum = BTC[t_signal] / BTC[t_signal - lookback] - 1
si abs(momentum) >= threshold:
  momentum > 0 -> comprar Up
  momentum < 0 -> comprar Down
```

Fee taker:

```text
fee = 0.07 * entry_price * (1 - entry_price)
pnl_net = win - entry_price - fee
```

Grid:

```text
lookback_min = 1,2,3,5,10,15,30
gap_min = 0,1,2
entry_t_s = 0,10,30,60
threshold = 0,0.0005,0.001,0.002
```

Splits:

```text
train = primer 50%
validation = siguiente 20%
holdout_lab = ultimo 30%
```

Nota: `holdout_lab` NO es holdout limpio; BTC ya fue inspeccionado.

## Resultado 1 - proxy con tolerancia 90s

Fuente:

```text
reports/phases/momentum_lookback_scan_proxy_prices.csv
reports/phases/momentum_lookback_scan_report.json
```

Mejor familia:

```text
lookback = 1-2 min
gap = 0
threshold = 0.0005 a 0.001
entry_t = 0s o 10s
```

Ejemplo fuerte:

```text
rule_id = proxy_L1_G0_E10_T0.0005_S0.0
train:      n=1400, acc=0.6386, mean_net_pnl=0.1159, ci95_low=0.0913
validation: n=700,  acc=0.6629, mean_net_pnl=0.1401, ci95_low=0.1046
holdout_lab:n=917,  acc=0.6554, mean_net_pnl=0.1358, ci95_low=0.1055
```

Problema:

```text
validation mean_entry_delay_s = 14.1s
```

Con proxy 90s, la entrada muchas veces ocurre bastante despues de `entry_t`. Eso puede ser una oportunidad de latencia, pero no demuestra que se pueda cruzar el ask a ese precio.

## Resultado 2 - proxy estricto 5s

Fuente:

```text
reports/phases/momentum_lookback_scan_proxy_prices_strict5s.csv
reports/phases/momentum_lookback_scan_report_strict5s.json
```

Con `proxy_staleness_s = 5`, el universo baja:

```text
proxy_windows: 5,600
```

No hubo reglas proxy que pasaran train+validation con `min_n_proxy=300`.

Corrida de sensibilidad con `min_n_proxy=50`:

```text
reports/phases/momentum_lookback_scan_proxy_prices_strict5s_minn50.csv
```

Muestra senales puntuales, pero con train pequenio o validation pequenio. No es suficiente para preregistrar una regla fuerte.

## Resultado 3 - orderbook ejecutable

Fuente:

```text
reports/phases/momentum_lookback_scan_orderbook_costed.csv
reports/phases/momentum_lookback_scan_orderbook_costed_strict5s.csv
```

El orderbook usa:

```text
Up entry = best_ask_up
Down entry = best_ask_down
staleness <= 5s
ask_size_threshold = 1,100,1000
```

No hubo regla que pasara criterios robustos:

```text
bootstrap_p_bonferroni_validation = 1.0 en los mejores candidatos
ci95_net_low_validation cruza 0
varias reglas con validation positiva tienen train negativo
```

Ejemplo:

```text
rule_id = orderbook_L1_G0_E30_T0.0_S1000.0
train:      mean_net_pnl=-0.0345, ci95_low=-0.1013
validation: mean_net_pnl= 0.0885, ci95_low=-0.0207
```

## Interpretacion

El escaneo si encontro una forma de aumentar el resultado proxy del momentum:

```text
de lookback 5m sin umbral
a lookback 1-2m con threshold pequeno
```

Pero el resultado fuerte vive en el precio proxy con tolerancia amplia. Cuando pedimos ejecucion mas estricta, la senal no queda confirmada.

## Decision

1. No declarar edge ejecutable.
2. No usar el proxy 90s como backtest de trading real.
3. Abrir una hipotesis nueva y mas precisa:

```text
H_LATENCY_001:
  El mercado Polymarket BTC 15m reacciona con retraso de segundos/minutos
  al momentum BTC spot, y ese retraso podria ser explotable si hay ask real
  disponible antes de que el precio se ajuste.
```

## Siguiente prueba correcta

Construir una tabla evento-a-evento para el periodo con orderbook:

```text
para cada ventana y cada segundo 0..120:
  BTC momentum observable antes de t
  best_ask_up/down real
  spread
  size
  delay desde ultimo cambio de precio PM
  pnl a resolution
```

Esto debe probar si el edge proxy es:

```text
1. stale pricing ejecutable
2. artefacto del feed `prices`
3. senal real pero sin liquidez suficiente
```
