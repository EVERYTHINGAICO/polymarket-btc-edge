# Fase 6 Sample Data Report

## resultado
DEMO

## resumen
No existía `data/observations.db` al inicio.
Se ejecutó una corrida smoke acotada permitida del logger:

```bash
python3 -m src.logger --demo-once --db data/observations.db --log-path reports/live/logger_runtime.log
```

La muestra generada es **DEMO / synthetic runtime scaffold**, no recolección real de mercado.
No debe tratarse como evidencia de captura live oficial.

## archivo SQLite
- `data/observations.db`

## filas encontradas
- 1

## 5 filas de muestra
Solo existe 1 fila actualmente:

```json
[
  {
    "window_id": "demo-window",
    "ts_open": "2026-05-25T20:30:00Z",
    "price_to_beat": 65000.0,
    "pm_up_price_open": 0.51,
    "deribit_index_open": 65010.0,
    "D_5m_otm_dotm": 0.5,
    "D_10m_otm_dotm": 0.5,
    "D_15m_otm_dotm": 0.5,
    "D_5m_atm": 0.0,
    "D_10m_atm": 0.0,
    "D_15m_atm": 0.0,
    "V_5m_otm_dotm": 0.5,
    "V_10m_otm_dotm": 0.5,
    "V_15m_otm_dotm": 0.5,
    "n_trades_5m": 1,
    "n_trades_10m": 1,
    "n_trades_15m": 1,
    "ts_close": "2026-05-25T20:45:00Z",
    "deribit_index_close": 0.0,
    "chainlink_close": 0.0,
    "outcome": "Down",
    "pm_up_price_close": 0.0,
    "is_incomplete": 1,
    "insufficient_flow": 1,
    "notes": "demo_runtime_error"
  }
]
```

## campos presentes
- `window_id`
- `ts_open`
- `price_to_beat`
- `pm_up_price_open`
- `deribit_index_open`
- `D_5m_otm_dotm`
- `D_10m_otm_dotm`
- `D_15m_otm_dotm`
- `D_5m_atm`
- `D_10m_atm`
- `D_15m_atm`
- `V_5m_otm_dotm`
- `V_10m_otm_dotm`
- `V_15m_otm_dotm`
- `n_trades_5m`
- `n_trades_10m`
- `n_trades_15m`
- `ts_close`
- `deribit_index_close`
- `chainlink_close`
- `outcome`
- `pm_up_price_close`
- `is_incomplete`
- `insufficient_flow`
- `notes`

## campos faltantes
- Ninguno respecto al esquema actual de `observations`.

## evaluación para análisis posterior
- **Sí sirve parcialmente** para validar el formato/shape del registro y la estructura de la SQLite.
- **No sirve** para análisis estadístico ni para validar captura real de mercado.
- Señales claras de que es demo:
  - `window_id = demo-window`
  - `notes = demo_runtime_error`
  - `is_incomplete = 1`
  - `insufficient_flow = 1`
  - `chainlink_close = 0.0`
  - `deribit_index_close = 0.0`

## siguiente acción recomendada
Ejecutar una corrida smoke **real y supervisada** del runtime read-only que produzca unas pocas ventanas live o semi-live inspeccionables, sin iniciar todavía recolección prolongada de 10–14 días. Esa corrida debe dejar filas no-demo con timestamps/índices/precios observados realmente.
