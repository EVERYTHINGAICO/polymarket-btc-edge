# Fase 7 Forward Rules Freeze — 2026-06-03

## Estado

PASS

## Decision

Pedro congelo tres reglas para evaluacion forward. No se permite optimizar
parametros con la muestra ya observada.

## Corte experimental

- Denominador observado antes del freeze: 597 ventanas completas.
- Fuente usada en el analisis proxy: `deribit_trades_raw.index_price`.
- Staleness maximo: 60s.
- Sin orderbook.
- Veredicto aceptado: el patron historico/proxy no replica live de forma
  robusta con Deribit index. Mantener recoleccion; no operar.

## Reglas congeladas

- `RULE_A`: lookback=1, gap=0, threshold=0.0005, entry=30s.
- `RULE_B`: lookback=2, gap=0, threshold=0.001, entry=30s.
- `RULE_BASELINE`: lookback=5, gap=0, threshold=0, entry=30s.

## Forward policy

Evaluar solo ventanas nuevas posteriores a:

`2026-06-03T07:15:00Z`

Condiciones de reporte:

- `n >= 1000` por regla, o
- al menos 7 dias adicionales de datos.

Metricas requeridas:

- n
- accuracy
- mean_net_pnl
- CI95 bootstrap
- p_boot
- por dia
- por hora UTC
- staleness promedio
- coverage

## Datos faltantes para superar el limite proxy

- Spot/Chainlink o Binance 1m continuo.
- Orderbook Polymarket: best ask/bid y size para Up/Down.
- Precios intrawindow mas frecuentes durante los primeros 120s.

## Limite de veredicto

Sin orderbook, el maximo veredicto permitido sigue siendo:

`proxy estadistico, no edge ejecutable`
