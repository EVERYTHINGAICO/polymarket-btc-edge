# backfill/ — Experiment 2: historical backfill (Dec 2025 – Apr 2026)

Reproducible historical analysis of **9,225 Polymarket BTC Up/Down 15-minute
windows** with full Deribit options trade history (1,491,915 trades),
Chainlink BTC/USD references, and Polymarket intra-window tick trajectories
(880,587 ticks).

This is the independent, frozen-data counterpart to [`../live/`](../live/).
It allowed running ~26 candidate hypotheses against a fixed sample with
strict pre-registration, temporal hold-out, and Bonferroni correction.

**Period covered**: 2025-12-26 → 2026-04-21 (117 days).
**Status**: closed. Verdict: NO_EDGE_FIN for taker after costs.

---

## Why a separate experiment

The live logger captures forward-in-time data. Useful but slow (n=1000 takes
~10 days). The backfill experiment was started 2026-05-31 to:

1. Use **a totally separate dataset** (different period, different ingestion
   path) for replication.
2. **Allow exhaustive hypothesis search** (26 candidates: D variants,
   momentum, reversion, orderbook imbalance, market making, arbitrage, …)
   under multiple-comparisons discipline.
3. **Probe finer microstructure** (20.47M ticks at 0.1s + 866M orderbook
   snapshot rows — both in `data/raw/` which is `.gitignore`d).

---

## Pre-registration

[`analysis_config_v2.0.0_SIGNED_20260602T080755Z.json`](analysis_config_v2.0.0_SIGNED_20260602T080755Z.json)
— frozen 2026-06-02T08:07Z.

Key parameters (matching `live/` v1.0.0 where applicable):

| Parameter | Value |
|-----------|-------|
| Primary D variant | `D_15m_otm_dotm` |
| Threshold | `|D| > 5.0` |
| Train / hold-out split | `70 / 30` temporal (no random shuffle) |
| `min_n_for_verdict` | `1000` |
| Block bootstrap | `block_size = 10` (autocorrelation-aware) |
| Black-76 delta | recomputed (Deribit ticker delta not used) |
| IV filter | `0 < iv ≤ 300` |

Comparison with `live/` v1.0.0 in
[`docs/AUDITORIA_DATOS_vs_PLAN.md`](docs/AUDITORIA_DATOS_vs_PLAN.md):
3 deliberate differences documented (temporal split, BS-76, bootstrap).

---

## Reproducing the dataset

> **Heads-up**: the raw data (`data/raw/`, `data/interim/`, `data/processed/`)
> is NOT in git (3.8 GB). The scripts rebuild it deterministically from
> public APIs and pinned HuggingFace dataset revisions.

```bash
# 1. Setup
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# 2. Initialize empty DB schema
python scripts/init_db.py

# 3. Build the dataset (each step has a SHA256 manifest)
python scripts/build_windows.py            # 9,231 windows from HF dataset (revision pinned)
python scripts/build_outcomes.py           # 9,231/9,231 resolved via CLOB
python scripts/build_deribit_trades.py     # 1,491,915 trades from history.deribit.com
python scripts/build_deribit_features.py   # D variants (anti-lookahead, fixed 2026-06-02)
python scripts/build_polymarket_prices.py  # pm_up_price_open + trajectory
python scripts/build_chainlink_refs.py     # chainlink_close + price_to_beat
python scripts/merge_research_dataset.py   # consolidates to research_dataset_v1.parquet
python scripts/load_to_db.py               # populates observations DB

# 4. Run the official analysis
python scripts/run_analysis_exp2.py
```

---

## Key scripts

### Build / ingest
| Script | Output |
|--------|--------|
| `build_windows.py` | 9,231 windows |
| `build_outcomes.py` | 9,231 outcomes via CLOB |
| `build_deribit_trades.py` | 1,491,915 trades |
| `build_deribit_features.py` | D/V variants (predictive, no lookahead) |
| `build_polymarket_prices.py` | pm_up_price_open + 880k trajectory ticks |
| `build_chainlink_refs.py` | 9,231 chainlink_close + price_to_beat |
| `merge_research_dataset.py` | consolidated parquet |

### Analysis / scans
| Script | Purpose |
|--------|---------|
| `run_analysis_exp2.py` | Official 5-gate analysis with temporal split + block bootstrap |
| `audit_momentum_signal.py` | Reproduces the (now-retracted) momentum 54% finding and dissects it |
| `explore_edge_candidates.py` | TRAIN-only exploration of candidates B (PM momentum/reversion) and V (volatility) |
| `test_candidate_B_reversion_60_60_holdout.py` | Sealed hold-out test of one PM-reversion candidate |
| `scan_momentum_lookbacks_costed.py` | Sweep of momentum lookback windows with realistic costs |
| `scan_orderbook_imbalance_i1.py` | Orderbook imbalance scan |
| `scan_orderbook_arbitrage_s1.py` | Arbitrage scan |
| `scan_market_making_m1.py` | Market-making scan — **the least-refuted candidate** |
| `study_maker.py` | Dedicated study of maker side economics |

---

## Documentation

22 technical documents in [`docs/`](docs/) — entry points:

- [`docs/ESTADO_PROYECTO.md`](docs/ESTADO_PROYECTO.md) — living status snapshot.
- [`docs/HALLAZGOS_DATOS_FINOS.md`](docs/HALLAZGOS_DATOS_FINOS.md) — tick + orderbook findings (where the "market is efficient for taker" conclusion lives).
- [`docs/AUDITORIA_PROTOCOLO.md`](docs/AUDITORIA_PROTOCOLO.md) — Harvard-case treatment of 6 degrees of freedom frozen before observation.
- [`docs/PRE_REGISTRO_v2.0.0.md`](docs/PRE_REGISTRO_v2.0.0.md) — verbose form of the pre-registration.
- [`docs/COMPARACION_EXP1_EXP2.md`](docs/COMPARACION_EXP1_EXP2.md) — cross-experiment comparison.
- [`docs/ESTUDIO_MOMENTUM.md`](docs/ESTUDIO_MOMENTUM.md) — the momentum hypothesis writeup (with retraction).

Spanish documentation throughout. (The codebase comments and identifiers are English.)

---

## Tests

```bash
python -m pytest tests/ -v
# tests/test_analysis_fixtures.py    16/16 PASS  (synthetic fixtures from Exp1)
# tests/test_bootstrap.py            block bootstrap with autocorrelated data
# tests/test_no_lookahead.py          3/3 PASS — asserts no input has ts >= ts_open
```

---

## What didn't make the repo

- `data/raw/` (~2.4 GB): trades, orderbook, Binance prices. Reproducible.
- `data/interim/` (~1 GB): intermediate parquets. Reproducible.
- `data/processed/` (~400 MB): final `research_dataset_v1.parquet`. Reproducible.
- `.hf_cache_orderbook/`: HuggingFace download cache.
- One 535 MB CSV with paired orderbook snapshots (`s1_pilot_paired_snapshots_spread_100.csv`). Reproducible from `scripts/pilot_orderbook_arbitrage_s1.py`.
