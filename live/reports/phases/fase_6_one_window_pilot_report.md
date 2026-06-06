# Fase 6 One-Window Pilot Report

## estado
INCOMPLETE_REAL

## resumen
Se auditó y corrigió la fila abierta del piloto real `btc-updown-15m-1779828300`.
El piloto anterior logró escribir un open snapshot real en SQLite, pero falló antes del close snapshot.
No se inventó ningún cierre.

## fila auditada
- `window_id`: `btc-updown-15m-1779828300`
- `ts_open`: `2026-05-26T20:45:00Z`
- `ts_close`: `NULL` al momento de la auditoría inicial

## corrección aplicada
La fila abierta fue marcada conservadoramente como incompleta:
- `is_incomplete = 1`
- `insufficient_flow = 1`
- `notes` incluye:
  - `runtime_error`
  - `missing_close_snapshot`
  - `deribit_ws_timeout`
  - `missing_chainlink_close`

## criterio
Esto evita que una ventana abierta quede presentada como fila limpia cuando el proceso falla post-open.

## cambios de runtime
Se implementó cleanup automático post-open en `scripts/one_window_pilot.py` y `src/logger.py` para que cualquier excepción después del open snapshot marque la fila como incompleta.

## limitaciones
- No se obtuvo close snapshot real en este piloto.
- No se reintentó una nueva ventana.
- No se marcó PASS completo.

## siguiente paso recomendado
Corregir la robustez del loop de captura Deribit durante la ventana y recién después reintentar un único piloto real supervisado.
