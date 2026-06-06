# Momentum audit report

Run UTC: `2026-06-03T06:14:57.933418Z`

## Primary population

`all_windows` = BTC 15m windows joined from raw markets + CLOB outcomes + pm open price.

Formula:

```text
ts_open = end_ts - 900
momentum_5m = Binance_close[ts_open] - Binance_close[ts_open - 300s]
predict Up if momentum_5m > 0, Down if momentum_5m < 0
split = chronological 70/30 before dropping zero momentum
```

## Result

| split | n | accuracy | binom p | mean entry+fee | acc - breakeven | mean net pnl | net bootstrap p |
|---|---:|---:|---:|---:|---:|---:|---:|
| train | 6,432 | 0.5362 | 3.306e-09 | 0.5052 | 0.0310 | 0.0310 | 0 |
| holdout | 2,769 | 0.5421 | 5.137e-06 | 0.5068 | 0.0353 | 0.0353 | 0 |
| all | 9,201 | 0.5380 | 1.667e-13 | 0.5057 | 0.0323 | 0.0323 | 0 |

## Compare with ESTUDIO_MOMENTUM.md

- Document claim holdout n: `2769`
- Reproduced holdout n: `2769`
- Document claim holdout accuracy: `0.5421`
- Reproduced holdout accuracy: `0.5421`
- Accuracy delta: `-0.0000`
- Document claim break-even accuracy: `0.5270`
- Reproduced break-even under `entry*(1+0.018)`: `0.5068`
- Break-even delta: `-0.0202`

## Holdout threshold diagnostic

| abs momentum ret threshold | n | coverage | accuracy |
|---:|---:|---:|---:|
| 0.0000 | 2,769 | 1.0000 | 0.5421 |
| 0.0010 | 844 | 0.3048 | 0.5960 |
| 0.0020 | 263 | 0.0950 | 0.6008 |

## Holdout mechanism diagnostic

- Pearson corr(momentum_ret, pm_open - 0.5): `-0.1021` (p=`7.277e-08`, n=`2769`)

| regime | n | realized P(Up) | mean pm Up price | Up gap | Down gap |
|---|---:|---:|---:|---:|---:|
| bullish_momentum | 1,379 | 0.5526 | 0.4978 | +0.0548 | -0.0548 |
| bearish_momentum | 1,390 | 0.4683 | 0.5022 | -0.0338 | +0.0338 |

## Momentum vs PM open-price signal

- Agree: n=`405`, momentum accuracy=`0.5703703703703704`
- Disagree: n=`529`, momentum accuracy=`0.497164461247637`

## Momentum vs BTC price_to_beat signal

- Agree: n=`1810`, momentum accuracy=`0.5779005524861879`
- Disagree: n=`959`, momentum accuracy=`0.4744525547445255`

## Verdict

This report reproduces the exact BTC momentum rule on local data. It does not confirm an independent edge because this is still the previously touched BTC sample. Independent ETH/SOL/live data remain required.
