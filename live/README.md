# live/ — Experiment 1: continuous live capture

Continuous read-only logger of Polymarket BTC Up/Down 15-minute windows
joined with Deribit BTC options order flow (D signal), Chainlink BTC/USD
reference (Polygon mainnet aggregator) and intra-window PM price trajectory.

**Period covered**: May 2026 – ongoing.
**Capture rhythm**: ~4 windows/hour (96 windows/day, aligned to UTC `:00 :15 :30 :45`).
**Status at v0.9-beta**: ~680 windows captured. Target n=1000 → ETA ~2026-06-07.

---

## Quick start

```bash
# 1. Create venv + install deps
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# 2. Initialize empty SQLite (the loggers will populate it)
python -m src.db init --db data/observations.db

# 3a. Run a single window pilot (~22 minutes)
python -m src.logger --one-window-pilot --with-trajectory \
    --db data/observations.db --log-path reports/live/pilot.log

# 3b. Run continuous capture (blocks; Ctrl-C for clean shutdown)
python -m src.logger --continuous --with-trajectory \
    --db data/observations.db --log-path reports/live/continuous_logger.log

# 4. Analyze (whenever n >= min_n_for_verdict in pre-registration)
python scripts/run_analysis.py \
    --output reports/phases/fase_7_analysis_$(date -u +%Y-%m-%d).json
```

---

## Pre-registration (frozen)

[`analysis_config.json`](analysis_config.json) — v1.0.0, frozen 2026-05-30T00:00:00Z.

Key parameters (all locked before observing hold-out):

| Parameter | Value | Source |
|-----------|-------|--------|
| Primary D variant | `D_15m_otm_dotm` | Paper Alexander 2022 |
| Threshold `|D| > x` | `5.0` | Empirical from Exp1 preliminaries |
| α (Gate 1) | `0.05` | Standard |
| N tests for Bonferroni | `5` | 5 gates |
| `α_corrected` | `0.01` | `0.05 / 5` |
| Train / hold-out split | `70 / 30` deterministic by seed=42 | — |
| K-fold (sanity on train) | `n_splits=5, seed=42` | — |
| `min_n_for_verdict` | `1000` | Power analysis |
| Polymarket taker fee | `0.07` (7%) | Polymarket fee schedule |
| Spread | `0.01` | Conservative estimate |

The file is signed by its SHA256 hash; any modification after observation invalidates the experiment per `PROJECT_DESIGN.md` §0.

---

## Module layout

| Path | Purpose |
|------|---------|
| `src/continuous_logger.py` | Main loop — 4 threads (Deribit WS, scheduler, intrawindow sampler, outcome resolver). |
| `src/deribit_feed.py` | Public WebSocket stream of `trades.option.BTC.100ms` + REST helpers. |
| `src/polymarket_feed.py` | Read-only CLOB/Gamma client: discover markets, midpoints, outcome polling. |
| `src/chainlink_feed.py` | Read-only Polygon RPC client for BTC/USD aggregator price. |
| `src/signal.py` | Rolling D/V buffer, thread-safe. |
| `src/signal_bs76.py` | Parallel D/V computation with recomputed Black-76 delta. |
| `src/intrawindow_sampler.py` | Per-window sampler of `pm_up_price` (sec-by-sec first 120s). |
| `src/raw_trade_logger.py` | Parallel persistence of raw Deribit trades for offline Black-76 backfill. |
| `src/db.py` | SQLite schema, migrations, WAL mode. |
| `src/analysis/` | Pure analytical core: `config`, `data`, `stats`, `gates`, `verdict`, `exploratory`. |

---

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/run_analysis.py` | CLI runner of the 5-gate analysis with deterministic output hash. |
| `scripts/backfill_bs76_from_history.py` | Reprocess captured windows with Black-76 from `history.deribit.com`. |
| `scripts/migrate_add_bs76_columns.py` | Additive ALTER TABLE for `*_bs76` columns. |
| `scripts/one_window_pilot.py` | Single-window pilot for sanity check. |
| `scripts/window_id_audit.py` | Verify window IDs against Polymarket source of truth. |
| `scripts/monitor_collection.py` | Live progress monitor. |

---

## Tests

```bash
python -m pytest tests/ -v
# Highlights:
#   tests/test_analysis_fixtures.py   16/16 PASS  (synthetic fixtures, known answers)
#   tests/test_signal_bs76.py         29/29 PASS  (Black-76 against known values)
#   tests/test_signal.py              D/V rolling buffer thread-safety
```

---

## Hard rules (do not violate)

- **READ-ONLY** access to Deribit, Polymarket, Chainlink. No trading APIs.
- **Do NOT** modify `analysis_config.json` after hold-out has been observed.
- **Do NOT** commit `data/`, `.env`, `*.db`, `*.log`.

---

## Data model (empty in this repo — populated at runtime)

SQLite database at `data/observations.db`:

- `observations` — window-level, one row per Polymarket 15m window.
- `observations_intrawindow` — PM price every second 0–120s, then every 30s.
- `deribit_trades_raw` — raw Deribit trades with `iv`, `index_price` for Black-76.

Full schema in `src/db.py`.
