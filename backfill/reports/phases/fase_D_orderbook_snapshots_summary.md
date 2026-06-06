# Fase D — Orderbook Snapshots Summary

Input:

- `data/raw/orderbook/btc15m_orderbook_part0.parquet`
- SHA256: `9688c28b15aff7707181835ccc3549f11d02fbccc0b67f1bde5d9865507f8c4a`

Output:

- `data/interim/orderbook_btc15m_snapshots.parquet`
- SHA256: `0ac142a2c0f416ea9d9e397cb3bbcf9006142fc97c327b51ff88e2589aee61cd`

Build command:

```bash
/tmp/exp2venv/bin/python scripts/build_orderbook_snapshots.py
```

## Counts

| Metric | Value |
|---|---:|
| Paired snapshots | 94,075,630 |
| Markets | 1,028 |
| min `ts_ms` | 1774848600009 |
| max `ts_ms` | 1776729431800 |
| `time_to_close_s` range | 0.001 .. 900.0 |
| bad `time_to_close_s` | 0 |

## Data Quality

| Check | Count |
|---|---:|
| `spread_up < 0` | 11,956 |
| `spread_down < 0` | 9,541 |
| negative prices | 0 |
| prices > 1 | 0 |
| null prices | 0 |
| any nonpositive size | 89,945,708 |

## Quantiles After Nonnegative Spread Filter

| Field | p01 | p05 | p50 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| `spread_up` | 0.001 | 0.010 | 0.010 | 0.020 | 0.470 |
| `spread_down` | 0.001 | 0.010 | 0.010 | 0.020 | 0.450 |
| `sum_asks` | 1.001 | 1.010 | 1.010 | 1.010 | 1.030 |

## Implication for M1

M1 must report two layers:

1. **Price-only proxy:** can market-making work if displayed prices are real?
2. **Executable proxy:** require positive displayed sizes.

Because most snapshots have at least one nonpositive displayed size, any claim of
tradable edge must be validated with ticks/fills, not only orderbook sizes.
