# Fase 7 Forward Collection Started — 2026-06-03

## Estado

PASS

## Procesos activos

El logger principal continuo sigue corriendo sin reinicio:

`py -m src.logger --continuous --with-trajectory --db ".../data/observations.db"`

Se agregaron dos sidecars aislados:

1. Raw Deribit:

`py -m src.raw_trade_logger --db ".../data/observations.db" --log-path ".../reports/live/raw_trade_logger.log"`

2. Forward market data:

`py scripts/collect_forward_market_data.py --db ".../data/observations.db" --log-path ".../reports/live/forward_market_data.log" --spot-interval-seconds 60 --orderbook-interval-seconds 5 --orderbook-max-seconds 120`

## Tablas nuevas

- `spot_prices`
- `orderbook`

## Objetivo

Recolectar datos faltantes sin modificar `analysis_config.json`:

- Chainlink/Binance spot 1m para momentum real futuro.
- Orderbook Polymarket de Up/Down para evaluar entrada ejecutable futura.
- Midpoint intrawindow mas frecuente durante los primeros 120s.

## Primer sanity

- `spot_prices` empezo a recibir muestras Chainlink y Binance.
- `deribit_trades_raw` volvio a crecer con raw trades live.
- `orderbook` queda listo; solo se puebla cuando el sidecar observa una ventana en sus primeros 120s.

## Regla de interpretacion

Sin orderbook suficiente, no declarar edge ejecutable.
