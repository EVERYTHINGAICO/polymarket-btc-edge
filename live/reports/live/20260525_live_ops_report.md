# Live Ops Report

## Resultado general
BLOCKED

## Runs ejecutados
- `python3 scripts/live_t1_deribit_capture.py --duration-minutes 0.02`
- `python3 scripts/live_t3_time_alignment.py --duration-minutes 0.02`
- `python3 scripts/live_t4_resilience_check.py --duration-minutes 0.02`
- `python3 scripts/live_collection_supervisor.py --duration-minutes 15`

## Repos consultados
- RiveChen/deribit-historical-data
- BarendPotijk/deribit_historical_trades
- nostoz/deribit_volatility_download_and_visualize
- fshahy/dankbit
- bottama/cryptocurrency-derivatives-pricing-and-delta-neutral-volatility-trading

## Patrones reutilizados
- Deribit WebSocket público v2
- `public/subscribe`
- captura read-only de trades de opciones BTC
- parsing conservador de `instrument_name`, `direction`, `delta`
- retry básico sin trading ni escritura externa

## Resultados
- T1: `BLOCKED_MISSING_DEPENDENCY`
  - Falta `websockets` en el runtime.
  - `python3 -m pip` no existe.
  - `python3 -m venv` falla por ausencia de `ensurepip`.
- T3: `BLOCKED_ENDPOINT_UNCONFIRMED`
  - `https://clob.polymarket.com` y `https://gamma-api.polymarket.com/markets?limit=1` devolvieron `403`.
  - No quedó confirmado endpoint público confiable para ventana activa/price_to_beat.
- T4: `PENDING_MANUAL_NETWORK_CUT`
- Supervisor: `PENDING_HUMAN_CONFIRMATION`

## Logs y JSON generados
- `reports/live/t1_deribit_capture_result.json`
- `reports/live/t3_time_alignment_result.json`
- `reports/live/t4_resilience_check_result.json`
- `reports/live/live_collection_supervisor_result.json`
- `reports/live/20260525_reference_consult_report.md`
- `reports/phases/fase_5v_validation_status.json`

## Acción recomendada
1. Habilitar `websockets` en el runtime con uno de los comandos documentados en `20260525_reference_consult_report.md`.
2. Confirmar endpoint oficial read-only de Polymarket para ventana activa/price_to_beat desde docs o acceso permitido.
3. Repetir smoke tests.
4. Solo si T1 smoke pasa, lanzar T1 real de 60 minutos.
