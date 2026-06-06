# M1_RULE_001 - preregistro antes de holdout

Fecha local: 2026-06-02

## Estado

Regla congelada para una prueba holdout unica. No se permite ajustar umbrales despues de ver holdout.

## Dataset

- Input: `data/interim/orderbook_m1_samples_10s.parquet`
- SHA256: `ea58be7c4a30bcfebbee666f1a241bed7d146e42bf1232c36feb069a869dadab`
- Construccion: primera observacion valida por mercado, lado y bucket de 10s.
- Split: mercados ordenados por `ts_open`; TRAIN = primer 70%, HOLDOUT = ultimo 30%.

## Regla congelada

Evaluar cada token/lado (`Up`, `Down`) en la grilla de decision de 10s.

Condiciones de entrada:

```text
horizon_s = 30
spread >= 0.10
book_size = least(best_bid_size, best_ask_size) >= 1000
time_to_close_s >= 300
```

Target proxy:

```text
EV_proxy = spread / 2 - abs(future_mid - mid_now)
```

El `future_mid` debe venir de la primera muestra disponible despues de al menos 30s desde `ts_ms`, con tolerancia maxima de 20s.

## Unidad estadistica

La unidad primaria es `market_id`.

Proceso:

1. Calcular `EV_proxy` por decision elegible.
2. Promediar por `market_id`.
3. Testear si la media de mercados es mayor que 0.

No se cuentan decisiones/snapshots como observaciones independientes para el p-value final.

## Evidencia TRAIN que motivo la regla

Fuente: `reports/phases/m1_market_making_scan_train_samples10s.csv`

```text
horizon_s = 30
spread_threshold = 0.10
book_size_threshold = 1000
time_to_close_threshold = 300
n_markets = 420
n_decisions = 743
mean_market_ev_proxy = 0.012219
ci95_market_ev_low = 0.005067
ci95_market_ev_high = 0.019607
market_positive_rate = 0.571429
bootstrap_p_greater = 0.0000
bootstrap_p_bonferroni = 0.0000
```

## Criterio de avance

La regla avanza a simulacion T1 de fills/ticks solo si en HOLDOUT:

```text
n_markets >= 100
mean_market_ev_proxy > 0
ci95_market_ev_low > 0
bootstrap_p_greater < 0.05
```

Aunque pase, esto NO declara edge tradable. Solo habilita la siguiente fase:

```text
T1 = simulacion con fills, queue/adverse selection, fees, latencia y capacidad.
```
