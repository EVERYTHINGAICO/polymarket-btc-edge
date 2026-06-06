# M1_RULE_001 - veredicto holdout

Fecha local: 2026-06-02

## Veredicto

```text
NO_EDGE_CONFIRMADO
```

La regla tuvo EV_proxy medio positivo en HOLDOUT, pero no paso el criterio preregistrado porque el intervalo de confianza cruza cero y el bootstrap p-value no es menor que 0.05.

## Regla probada

Fuente del preregistro: `reports/phases/m1_rule_001_preregistration.md`

```text
horizon_s = 30
spread >= 0.10
book_size >= 1000
time_to_close_s >= 300
future_staleness_s = 20
unidad estadistica = market_id
```

## Resultado TRAIN

Fuente: `reports/phases/m1_market_making_scan_train_samples10s.csv`

```text
n_markets = 420
n_decisions = 743
mean_market_ev_proxy = 0.012219
ci95_market_ev_low = 0.005067
ci95_market_ev_high = 0.019607
market_positive_rate = 0.571429
bootstrap_p_greater = 0.0000
bootstrap_p_bonferroni = 0.0000
```

## Resultado HOLDOUT

Fuente: `reports/phases/m1_market_making_scan_holdout_samples10s.csv`

```text
n_markets = 166
n_decisions = 266
mean_market_ev_proxy = 0.007846
median_market_ev_proxy = 0.005000
ci95_market_ev_low = -0.007048
ci95_market_ev_high = 0.021711
market_positive_rate = 0.560241
bootstrap_p_greater = 0.141
ttest_p_greater = 0.142484
mean_spread = 0.554474
median_spread = 0.520000
median_book_size = 7381.33
mean_future_delta_s = 34.868169
```

## Interpretacion

La senal no se puede declarar como ventaja estadistica. La media positiva sugiere que hay estructura en spreads anchos, pero con esta muestra no podemos distinguirla de varianza con suficiente rigor.

Tambien sigue siendo solo `EV_proxy`: no incluye fills, queue position, fees, latencia ni inventario. Como no paso holdout, no se justifica avanzar esta regla a T1 como candidata principal.

## Decision

1. Archivar `M1_RULE_001` como fallida en confirmacion.
2. No ajustar sus umbrales usando holdout.
3. Abrir la siguiente hipotesis en TRAIN: `H3 order-flow / tick imbalance`.

## Siguiente experimento recomendado

`H3_TRAIN_001`:

```text
Pregunta:
  El flujo de compras/ventas en los ultimos 10s/30s/60s predice movimiento de mid
  suficiente para superar spread/costos?

Unidad:
  market_id

Features observables:
  buy_volume_10s, sell_volume_10s, imbalance_10s
  buy_volume_30s, sell_volume_30s, imbalance_30s
  trade_count_10s/30s/60s
  large_trade_flag

Targets:
  mid move 30s/60s/120s
  EV despues de cruzar spread o despues de maker fill proxy

Regla:
  Solo TRAIN. Si aparece candidato, preregistrar uno y correr holdout una vez.
```
