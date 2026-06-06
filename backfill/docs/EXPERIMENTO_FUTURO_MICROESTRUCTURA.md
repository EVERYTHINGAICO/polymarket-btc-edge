---
doc_id: EXPERIMENTO_FUTURO_MICROESTRUCTURA
rol: trabajo-futuro
estado: parqueado (no se trabaja hoy)
fase: Exp3 (futuro)
version: 1.0
creado: 2026-06-01
actualizado: 2026-06-01
uso: plan del experimento futuro (microestructura, orderbook, EV/backtest, ML)
---

# EXPERIMENTO FUTURO (Exp3) — Microestructura y lead-lag Deribit↔Polymarket

> **Estado:** PENDIENTE. NO se trabaja hoy. Guardado el 2026-06-01 a pedido de Pedro.
> **Precondición de arranque:** que Exp2 (replicar D, ver [`PLAN_EXP2.md`](PLAN_EXP2.md)) termine con un veredicto. Idealmente que haya señal (`EDGE_VALIDATED` o accuracy exploratoria prometedora). Si Exp2 da `NO_EDGE_FIN` rotundo, reconsiderar si vale la pena.
> **Por qué se separa:** este plan es más amplio que la pregunta de D y, sobre todo, su versión original (de Codex) decía "mira P(UP|D) y después decide" — eso es elegir hipótesis tras ver datos (cherry-picking). Aquí se hace bien: pre-registro + holdout sellado.

## Tesis (distinta de Exp2)

Exp2 pregunta *¿D predice el outcome?*. Exp3 pregunta algo más fino:

> **¿Deribit predice ERRORES DE PRECIO (desalineaciones temporales / lead-lag) en Polymarket?**
> Es decir: cuando el mercado profesional de opciones se mueve, ¿Polymarket tarda en ajustar, dejando una ventana explotable?

Esto vive sobre el **movimiento intra-ventana de `pm_up_price`**, no solo sobre el outcome final. Abre estrategias B/C/D (take-profit / stop-loss / entrada tardía) que Exp2 no considera.

## Features adicionales (no usados en Exp2)

Aprovechan datos que el backfill HF ya tiene pero que Exp2 ignora:

- **Polymarket microestructura:** `up_price_open/mid/preclose/max/min`, `volume_15m`, `trade_count_15m`, `spread_avg`, `spread_preclose`, `orderbook_imbalance`, `large_trade_flow`.
- **Deribit derivados:** `D_open/mid/change`, `atm_iv`, `iv_change`, `put_call_skew`, `option_volume_15m`, `open_interest`, `oi_change`.
- **Subyacente:** `btc_return_15m`, `realized_vol` (de `spot_prices`, velas 1m Binance).

## Plan de quant desk (6 fases, del research del 2026-06-01)

1. **Base maestra** — `windows_15m.parquet`, 1 fila por ventana (igual que Exp2, reusable).
2. **Features Polymarket** — qué creía el mercado ANTES del cierre.
3. **Features Deribit** — qué decía el mercado profesional ANTES del cierre.
4. **Asof join sin lookahead** — features solo con `timestamp ≤ end_ts - 30s`.
5. **Matemática primero (sin ML):** `P(UP|D alto)`, `P(UP|skew>0)`, `P(UP|D alto + IV↑)`, luego `EV = P(win)·payout − P(loss)·cost`.
6. **Backtest realista:** reglas simples (`D>umbral ∧ up_price<P_estimada → BUY UP`), métricas: accuracy, ROI, EV, Sharpe, max drawdown, hit rate por decil, profit factor, slippage, spread cost.
7. **Solo después:** ML.

## Rigor exigido (NO repetir el error de "mira y decide")

- **Pre-registrar** la hipótesis y umbrales ANTES de la Fase 5. Las exploraciones tipo `P(UP|D)` se hacen **solo en train**.
- **Holdout temporal sellado** (últimos N meses) que no se toca hasta la corrida confirmatoria final.
- Todo lo que se mire antes de pre-registrar se reporta como **EXPLORATORIO**, no confirmatorio.
- Mismos datos que Exp2 → declarar el solape; la validación confirmatoria idealmente sobre periodo no usado en Exp2.

## Estructura de repo sugerida (de Codex, para cuando arranque)

`src/data_sources/{polymarket,deribit}.py`, `src/features/{polymarket_features,deribit_features,merge}.py`, `src/backtest/{rules,metrics}.py`, `notebooks/01..04`, `scripts/{download_polymarket,build_windows,build_features,run_backtest}.py`, `tests/{test_no_lookahead,test_windows}.py`. Stack: pandas, duckdb, pyarrow, numpy, scipy, matplotlib, tqdm, pydantic, jupyter.

## Reglas duras (siguen aplicando)

REGISTRA no opera. Read-only. Sin trading/wallets/keys. No es un bot. Sigue siendo VALIDACIÓN, no ejecución — la ejecución sería un Nivel 2 fuera de alcance.
