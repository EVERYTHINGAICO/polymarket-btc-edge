# S1 Pilot Interpretation — Orderbook Arbitrage

Run: `scripts/pilot_orderbook_arbitrage_s1.py --n-markets 100 --sample spread`

Local orderbook:
`data/raw/orderbook/btc15m_orderbook_part0.parquet`

## Result

The raw condition `ask_up + ask_down < 1` appears frequently, but most extreme
events have **displayed capacity = 0** and are not executable.

After requiring positive displayed pair capacity:

| Filter | Runs | Markets |
|---|---:|---:|
| capacity > 0 | 7 | 3 |
| capacity > 1 | 7 | 3 |
| capacity > 100 | 7 | 3 |
| capacity > 1000 | 7 | 3 |

Executable-looking opportunities:

- `sum_ask` range: 0.98 to 0.99
- gross edge: 1% to 2%
- duration: 0 ms in the snapshot data (single-snapshot opportunities)
- displayed capacity: 5,367 to 17,836
- break-even fee rate: ~1.01% to ~2.04%

Fee scenario:

| Fee model | Net-positive runs | Markets |
|---|---:|---:|
| 0% | 7 | 3 |
| 1% | 7 | 3 |
| 2% | 2 | 2 |
| 7% | 0 | 0 |

## Interpretation

S1 is **not a robust taker-arbitrage edge** under the old 7% fee model.

It may still be relevant for:

- maker economics,
- lower effective fees,
- ultra-low-latency execution,
- bots that can react to single-snapshot book states,
- inventory/market-making strategies that do not need to cross both asks.

## Decision

Do not move S1 directly to holdout as a taker strategy.

Next statistically serious path:

1. Test market-making / spread capture (`M1`).
2. Test Polymarket ticks/order-flow (`T1`).
3. Use S1 as a diagnostic for fleeting book inefficiencies, not as confirmed EV.
