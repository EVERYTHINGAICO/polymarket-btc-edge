# handoffs/ — chronological journey

Day-by-day handoff notes written **during** the research, not retrospectively.
They are preserved verbatim because **the methodological story is in the corrections**, not in the polished outcome.

The most valuable single document here is `2026-06-02_report_to_exp1_D_calculation.md` paired with the `live/` audit response: that exchange shows the **public detection and retraction of a lookahead-bias error** that had momentarily looked like a 60% accuracy edge.

---

## Reading order

| Date | File | What happened |
|------|------|---------------|
| 2026-05-27 | [`2026-05-27_live_first_real_window.md`](2026-05-27_live_first_real_window.md) | First real (non-demo) Polymarket window captured. Outcome = Up via gamma authority. |
| 2026-05-27 | [`2026-05-27_live_handoff_final.md`](2026-05-27_live_handoff_final.md) | Closure of G6.1 (real-window pass) milestone. |
| 2026-05-28 | [`2026-05-28_live_continuous_logger.md`](2026-05-28_live_continuous_logger.md) | Continuous live logger operational. PROJECT_DESIGN §9 met. |
| 2026-05-30 | [`2026-05-30_live_analysis_ready.md`](2026-05-30_live_analysis_ready.md) | Deterministic analysis infrastructure ready. 5 gates + SHA256 hash. Pre-registration v1.0.0 signed. |
| 2026-05-31 | [`2026-05-31_backfill_kickoff.md`](2026-05-31_backfill_kickoff.md) | Decision to kick off backfill experiment (Exp2). |
| 2026-06-01 | [`2026-06-01_backfill_reframing.md`](2026-06-01_backfill_reframing.md) | Backfill reframed: meta = build understanding, not protect edge. |
| 2026-06-01 | [`2026-06-01_live_status_n453.md`](2026-06-01_live_status_n453.md) | Live progress at n=453, all gates INSUFICIENTE as expected. |
| 2026-06-02 | [`2026-06-02_backfill_complete.md`](2026-06-02_backfill_complete.md) | Backfill build complete. 9,225 windows. First analysis showed apparent 60.7% — flagged for audit. |
| 2026-06-02 | [`2026-06-02_report_to_exp1_D_calculation.md`](2026-06-02_report_to_exp1_D_calculation.md) | ⚠ **The retracted alert.** Backfill team proposed Exp1 had a D-calculation bug. Live team verified: correlation 0.997, sign coincidence 96.7%. The bug was in the **backfill** lookahead, not in the live logger. |
| 2026-06-03 | [`2026-06-03_report_to_exp1_validate_momentum.md`](2026-06-03_report_to_exp1_validate_momentum.md) | Backfill team identifies momentum candidate (54.21% reported) and asks live for independent validation. Subsequent audit found this was also lookahead-biased; real anti-lookahead accuracy is ~49–53%. |

---

## Methodology lessons captured by these handoffs

1. **Pre-registration matters in practice, not just on paper.**
   The frozen `analysis_config.json` survived the temptation to "adjust the threshold" when preliminary numbers suggested a 60% accuracy. The published verdict will be honest.

2. **Lookahead bias hides in mundane data plumbing.**
   `close[ts_open]` on a 1-minute Binance candle is *not* the price at `ts_open`; it is the price at `ts_open + 59s`. Two independent pipelines exhibited a version of this.

3. **Independent replication is the only honest test.**
   The same hypothesis re-run on virgin data (live windows that the backfill team had not seen) revealed bias the original team had missed.

4. **A retraction is a feature, not a failure.**
   The fastest way to lose trust is to delete the inconvenient finding. These handoffs preserve it instead.

5. **Multiple comparisons consume the hold-out.**
   ~26 hypotheses tested against the backfill hold-out. A finding with p<0.05 there is roughly 73% likely to be one of the noise hits. Bonferroni × 26 corrects it; only the live experiment can confirm.

6. **Cost of operation rapidly closes apparent edge.**
   The clearest finding of the project: even when raw accuracy looks promising, the Polymarket contract price adjusts within ~60s, eating most of the spread between the prediction and the realized payoff.

---

## A note on language

The handoffs are in **Spanish**. The codebase, README files, and authority documents are in English. Spanish is preserved here because it is how the work was actually done; translating would degrade some of the in-the-moment reasoning.

For Spanish-fluent readers: the language helps; the technical content is the same.
For others: the structure of each handoff (status / decision / risk / open questions) translates well by inspection, and key terms (lookahead, hold-out, Bonferroni, etc.) are in English.
