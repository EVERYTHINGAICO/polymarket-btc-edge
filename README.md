# polymarket-btc-edge

> Pre-registered statistical investigation of Bitcoin options order flow
> (Deribit Net Buying Pressure / D signal) as a predictor for Polymarket BTC
> Up/Down 15-minute binary outcomes. Reproducible (SHA256 bit-exact),
> Bonferroni-corrected, with hold-out validation. 11 hypotheses tested over
> 9,225 historical windows (Dec 2025–Apr 2026) plus continuous live capture
> (May–Jun 2026). Findings include a publicly retracted lookahead-bias
> mistake — preserved in the handoffs as documentation of real research
> hygiene.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Status: v0.9-beta](https://img.shields.io/badge/status-v0.9--beta-orange.svg)](#status)

---

## TL;DR

- **Question**: Does the directional signal `D` from Deribit BTC options order flow predict the outcome of Polymarket BTC Up/Down 15-minute markets?
- **Method**: Two complementary experiments — `live/` (continuous capture, May–Jun 2026) + `backfill/` (historical Dec 2025–Apr 2026, 9,225 windows from CLOB-verified outcomes).
- **Pre-registration**: Hypothesis and thresholds frozen with SHA256-timestamped commit *before* looking at hold-out data.
- **Hypotheses tested**: 11 (D variants, momentum spot, PM reversion, orderbook imbalance, market making, …).
- **Verdict**: No edge for taker after realistic costs. The market is efficient. The retraction of an early "momentum 54%" finding due to lookahead bias is preserved in the handoffs.
- **Deliverable**: a reproducible methodology, not alpha.

---

## Reading paths

### For curious readers (≈ 10 min)
1. This README.
2. [`reports/REPORTE_COMPLETO_PROYECTO.md`](reports/REPORTE_COMPLETO_PROYECTO.md) — comprehensive recap of every hypothesis tested with verdict.
3. [`handoffs/README.md`](handoffs/README.md) — chronological journey including retractions.

### For technical reviewers (≈ 1 hour)
1. [`PROJECT_DESIGN.md`](PROJECT_DESIGN.md) — authority document (Spanish), specifies the 5 statistical gates.
2. [`live/README.md`](live/README.md) and [`backfill/README.md`](backfill/README.md) — how to run each side.
3. [`live/analysis_config.json`](live/analysis_config.json) — frozen pre-registration v1.0.0 (timestamped 2026-05-30T00:00:00Z).
4. [`backfill/analysis_config_v2.0.0_SIGNED_20260602T080755Z.json`](backfill/analysis_config_v2.0.0_SIGNED_20260602T080755Z.json) — frozen pre-registration v2.0.0.
5. [`live/src/analysis/gates.py`](live/src/analysis/gates.py) — the 5 hypothesis gates (Gate 1: D vs coin, Gate 2: D vs market, Gate 3: lead-lag, Gate 4a: Chainlink↔Deribit, Gate 4b: net of costs).
6. [`handoffs/`](handoffs/) in chronological order — read the retractions.

### For research collaborators
1. [`reports/REPORTE_COMPLETO_PROYECTO.md`](reports/REPORTE_COMPLETO_PROYECTO.md) — deep dive.
2. [`backfill/docs/AUDITORIA_PROTOCOLO.md`](backfill/docs/AUDITORIA_PROTOCOLO.md) — 6 degrees of freedom frozen by Harvard-case analysis.
3. Open an Issue to discuss next steps (Chainlink modeling, market-making study, ETH/SOL replication).

---

## Repository layout

```
polymarket-btc-edge/
├── README.md                          ← this file
├── PROJECT_DESIGN.md                  ← authority document (Spanish)
├── LICENSE                            ← MIT
├── .gitignore
│
├── live/                              ← Experiment 1: continuous live logger
│   ├── src/                              capture, signal, analysis, tests
│   ├── scripts/                          run_analysis.py, backfill_bs76, ...
│   ├── tests/                            16+29 fixtures (PASS)
│   ├── analysis_config.json              pre-registration v1.0.0 (FROZEN)
│   └── README.md
│
├── backfill/                          ← Experiment 2: historical Dec25–Apr26
│   ├── src/                              clone of analysis modules
│   ├── scripts/                          build_*, scan_*, audit_*
│   ├── docs/                             22 technical docs
│   ├── tests/                            no-lookahead + bootstrap
│   ├── analysis_config*.json             pre-registration v2.0.0 (SIGNED)
│   └── README.md
│
├── reports/                           ← consolidated final findings
│   └── REPORTE_COMPLETO_PROYECTO.md
│
└── handoffs/                          ← chronological journey, honest retractions
    ├── 2026-05-27_live_first_real_window.md
    ├── 2026-05-28_live_continuous_logger.md
    ├── 2026-05-30_live_analysis_ready.md
    ├── 2026-05-31_backfill_kickoff.md
    ├── 2026-06-01_*.md
    ├── 2026-06-02_*.md (includes a retracted D-calc alert)
    └── 2026-06-03_report_to_exp1_validate_momentum.md
```

---

## Key methodological choices

| Choice | What it means |
|--------|---------------|
| **Frozen pre-registration** | Hypothesis, variant, threshold, fee, min sample size — all locked in `analysis_config.json` with SHA256 + ISO timestamp *before* hold-out is observed. |
| **Bonferroni correction** | `α_corrected = α / N_tests` to compensate for multiple comparisons. |
| **Temporal hold-out** | First 70% of windows = train (exploratory only). Last 30% = sealed hold-out, observed once for the verdict. |
| **Bit-exact reproducibility** | Input hash = SHA256 of canonical CSV of input data. Output hash = SHA256 of result dict excluding `run_at_utc`. Two runs with same input + config → identical output_hash. |
| **Synthetic fixtures** | 16 + 29 unit tests with known-answer datasets verify the calculation pipeline is correct *before* it touches real data. |
| **No-lookahead tests** | `tests/test_no_lookahead.py` (backfill) asserts no input has timestamp ≥ `ts_open`. |
| **Read-only operation** | All API access is strictly read-only. No trading, no signing, no wallets. The system *registers*, it does not *operate*. |

---

## What the project demonstrates (independent of the null result)

- Disciplined research workflow on a noisy, adversarial dataset.
- Honest handling of a discovered bias (lookahead in momentum calculation, **publicly retracted** in `handoffs/2026-06-02_*.md`).
- Two independent pipelines (live capture + historical backfill) used to cross-validate.
- Code that is small, deterministic, and testable.
- A null result documented with the same rigor as a positive result would deserve.

---

## Status

**v0.9-beta** — code, pre-registration, and partial live capture are public.
Final verdict (n ≥ 1000 live windows) expected around **2026-06-07**.
`v1.0` will tag the final report and the closing commit.

---

## Theoretical foundation

Alexander, C., Deng, J., Feng, J., & Wan, H. (2022). *Net Buying Pressure and the Information in Bitcoin Option Trades*. **arXiv:2109.02776**.

The paper's modest claim ("directional signal in OTM/DOTM options, weak but present, decaying within ~1 hour") was the seed. The project's contribution is a disciplined empirical test in the specific economic setting of Polymarket binary resolution by Chainlink.

---

## Hard rules (PROJECT_DESIGN §0)

- READ-ONLY on every external source (Polymarket, Deribit, Chainlink, Binance).
- No trading, no signing, no wallets, no private keys.
- Pre-registration locked before observing hold-out.
- `analysis_config.json` modification after observing outcomes invalidates the experiment.

---

## License

- **Code** (`live/src/`, `live/scripts/`, `backfill/src/`, `backfill/scripts/`, `tests/`): MIT — see [`LICENSE`](LICENSE).
- **Documentation** (`handoffs/`, `backfill/docs/`, `reports/`): CC-BY 4.0 unless noted otherwise. Attribution: `@EVERYTHINGAICO / polymarket-btc-edge`.

---

## Contact

- **Maintainer**: [@EVERYTHINGAICO](https://github.com/EVERYTHINGAICO) — `contact@everythingaico.com`
- **Issues**: open in this repo
- **Citation**: `EVERYTHINGAICO. (2026). polymarket-btc-edge: pre-registered investigation of Bitcoin options order flow for Polymarket BTC 15m outcomes. GitHub. https://github.com/EVERYTHINGAICO/polymarket-btc-edge`

---

## Acknowledgments

The retracted "momentum 54%" finding was caught by the live experiment's anti-lookahead audit. Credit to bonereaper for sharp comments on Chainlink aggregation behavior and the operational reality of fast-line latency that informed the project's conclusions about market efficiency.
