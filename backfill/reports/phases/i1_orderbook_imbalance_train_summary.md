# I1 orderbook imbalance - TRAIN summary

Fecha local: 2026-06-02

## Veredicto

```text
NO_CANDIDATE_FOR_PREREGISTRATION
```

No se encontro una regla I1 suficientemente fuerte para congelar y llevar a holdout.

## Datos

- Input: `data/interim/orderbook_i1_samples_10s.parquet`
- SHA256: `15acde8692c0e83338ffb13ba1577c49746e0f93f4356b4715a0762350ee2d32`
- Rows: 168,450
- Markets: 1,028
- Construccion: primera observacion valida por mercado, lado y bucket de 10s.

## Pregunta

Si el tamanio visible en bid/ask esta desbalanceado, podemos comprar un token al `best_ask` y tener EV positivo contra `future_mid`?

Proxy:

```text
EV_taker_proxy = future_mid - best_ask
```

Este proxy ya paga el spread de entrada, pero aun no incluye fees, latencia ni fallo de fill.

## Grid TRAIN

Fuente: `reports/phases/i1_orderbook_imbalance_scan_train_i1_samples10s.csv`

```text
horizons = 30,60,120
modes = momentum,contrarian
imbalance_thresholds = 0.2,0.4,0.6,0.8
max_spreads = 0.01,0.02,0.05,0.10,0.20
ask_size_thresholds = 1,100,1000
time_to_close_thresholds = 120,300
min_markets = 50
n_rules_tested = 644
```

## Mejor resultado TRAIN

```text
horizon_s = 120
mode = contrarian
imbalance_threshold = 0.8
max_spread = 0.01
ask_size_threshold = 1
time_to_close_threshold = 300
n_markets = 63
n_decisions = 131
mean_market_ev_taker_proxy = 0.017077
ci95_market_ev_low = -0.005210
ci95_market_ev_high = 0.040416
market_positive_rate = 0.301587
bootstrap_p_greater = 0.0550
bootstrap_p_bonferroni = 1.0
```

## Por que no avanza

```text
uncorrected bootstrap_p < 0.05: 0 reglas
bonferroni bootstrap_p < 0.05: 0 reglas
ci95_market_ev_low > 0: 0 reglas
```

La mejor regla ni siquiera pasa p < 0.05 sin correccion, y el intervalo cruza cero. No hay candidato honesto para preregistrar.

## Decision

1. No correr holdout para I1.
2. No ajustar umbrales usando intuicion post-hoc.
3. Para H3 real, conseguir trades/prints de Polymarket:
   - timestamp
   - market_id/token_id
   - side/aggressor si existe
   - price
   - size

Sin trades, solo podemos seguir con variantes de orderbook, no con order-flow verdadero.
