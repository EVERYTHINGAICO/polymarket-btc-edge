# Momentum lookback costed scan

Run UTC: `2026-06-03T07:09:10.455776Z`

## Protocol

BTC is treated as a laboratory sample because it has already been inspected. A rule selected here still requires independent ETH/SOL/live validation.

Cost formula:

```text
taker_fee = fee_rate * entry_price * (1 - entry_price)
pnl_net = win - entry_price - taker_fee
```

Fee rate used: `0.07`

## Proxy Top Train+Validation

No paired proxy rules met minimum n.

## Orderbook Top Train+Validation

| rule_id | n_train | mean_net_pnl_train | ci95_net_low_train | bootstrap_p_bonferroni_train | n_validation | mean_net_pnl_validation | ci95_net_low_validation | bootstrap_p_bonferroni_validation | mean_entry_validation | mean_entry_delay_s_validation | median_capacity_validation | mean_spread_validation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| orderbook_L1_G0_E30_T0.0_S1000.0 | 199 | -0.0344649 | -0.101288 | 1 | 76 | 0.0884675 | -0.0207387 | 1 | 0.565658 | 0.0422763 | 19698.8 | 0.0171053 |
| orderbook_L1_G0_E30_T0.0_S1.0 | 200 | -0.0368301 | -0.106171 | 1 | 76 | 0.0884675 | -0.0207387 | 1 | 0.565658 | 0.0422763 | 19698.8 | 0.0171053 |
| orderbook_L1_G0_E30_T0.0_S100.0 | 200 | -0.0368301 | -0.106171 | 1 | 76 | 0.0884675 | -0.0207387 | 1 | 0.565658 | 0.0422763 | 19698.8 | 0.0171053 |
| orderbook_L2_G0_E0_T0.0_S1.0 | 219 | 0.00435716 | -0.0634934 | 1 | 93 | 0.0738183 | -0.0270137 | 1 | 0.510968 | 0.0184194 | 20435.4 | 0.0231183 |
| orderbook_L2_G0_E0_T0.0_S100.0 | 219 | 0.00435716 | -0.0634934 | 1 | 93 | 0.0738183 | -0.0270137 | 1 | 0.510968 | 0.0184194 | 20435.4 | 0.0231183 |
| orderbook_L2_G0_E0_T0.0_S1000.0 | 219 | 0.00435716 | -0.0634934 | 1 | 93 | 0.0738183 | -0.0270137 | 1 | 0.510968 | 0.0184194 | 20435.4 | 0.0231183 |
| orderbook_L5_G0_E0_T0.0005_S1.0 | 127 | -0.00877923 | -0.093423 | 1 | 61 | 0.0723026 | -0.0590025 | 1 | 0.500492 | 0.0186885 | 20360.5 | 0.0295082 |
| orderbook_L5_G0_E0_T0.0005_S100.0 | 127 | -0.00877923 | -0.093423 | 1 | 61 | 0.0723026 | -0.0590025 | 1 | 0.500492 | 0.0186885 | 20360.5 | 0.0295082 |
| orderbook_L5_G0_E0_T0.0005_S1000.0 | 127 | -0.00877923 | -0.093423 | 1 | 61 | 0.0723026 | -0.0590025 | 1 | 0.500492 | 0.0186885 | 20360.5 | 0.0295082 |
| orderbook_L30_G2_E0_T0.002_S1.0 | 84 | -0.0496775 | -0.155959 | 1 | 51 | 0.0709049 | -0.0669474 | 1 | 0.460784 | 0.017451 | 20382.5 | 0.0411765 |
| orderbook_L30_G2_E0_T0.002_S100.0 | 84 | -0.0496775 | -0.155959 | 1 | 51 | 0.0709049 | -0.0669474 | 1 | 0.460784 | 0.017451 | 20382.5 | 0.0411765 |
| orderbook_L30_G2_E0_T0.002_S1000.0 | 84 | -0.0496775 | -0.155959 | 1 | 51 | 0.0709049 | -0.0669474 | 1 | 0.460784 | 0.017451 | 20382.5 | 0.0411765 |
| orderbook_L1_G0_E0_T0.0_S100.0 | 224 | 0.0133412 | -0.0532429 | 1 | 97 | 0.059539 | -0.0383947 | 1 | 0.510722 | 0.0183608 | 20425.4 | 0.0227835 |
| orderbook_L1_G0_E0_T0.0_S1000.0 | 224 | 0.0133412 | -0.0532429 | 1 | 97 | 0.059539 | -0.0383947 | 1 | 0.510722 | 0.0183608 | 20425.4 | 0.0227835 |
| orderbook_L1_G0_E0_T0.0_S1.0 | 225 | 0.0109375 | -0.0542333 | 1 | 97 | 0.059539 | -0.0383947 | 1 | 0.510722 | 0.0183608 | 20425.4 | 0.0227835 |

## Files

- `reports/phases/momentum_lookback_scan_proxy_prices.csv`
- `reports/phases/momentum_lookback_scan_orderbook_costed.csv`
- `reports/phases/momentum_lookback_scan_report.json`
