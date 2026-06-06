---
doc_id: METRICAS_RENDIMIENTO
rol: bitacora
estado: exploratorio (dimensionamiento del edge)
fase: post-EXP2-9
version: 1.0
creado: 2026-06-02
uso: dimensionar el edge — rendimiento por apuesta, mercados/día. SOLO métricas bien definidas.
---

> # ⛔ INVALIDADO (2026-06-02) — estas métricas medían LOOKAHEAD
>
> El ROI +13%/apuesta y todo lo de abajo se calculó sobre el D **concurrente** (trades durante la ventana = lookahead bias). Con el D **predictivo correcto** (trades antes de ts_open), la accuracy es ~48% → **EV negativo, no hay rendimiento.** Estas métricas NO representan un edge real. Se conservan como registro del error.

---

# (INVALIDADO) Métricas de rendimiento — dimensionamiento del edge (histórico, exploratorio)

> **Naturaleza:** análisis exploratorio sobre el dataset histórico (dic-2025→abr-2026) para *dimensionar* el edge. NO es trading real ni promesa de resultados futuros. Sigue siendo VALIDACIÓN (PROJECT_DESIGN §0).
> **Estrategia evaluada:** la pre-registrada — `D_15m_otm_dotm`, `|D|>5`, apostar al lado de sign(D), 1 unidad de payoff por mercado.
> **Modelo de costos:** idéntico al Gate 4b oficial (verificado línea por línea): `net_pnl = win·1.0 − (entry+spread) − fee·(entry+spread)`, con `spread=0.01`, `fee=0.07`. Determinista (hash reproducible).

## Métricas (bien definidas, por-apuesta)

| Métrica | Valor |
|---------|-------|
| Apuestas (n) | 2.408 en 112 días |
| Accuracy / % ganadoras | **60.7%** |
| **EV neto / apuesta** | **+0.064** unidades de payoff (= Gate 4b oficial) |
| **ROI / apuesta** (sobre capital arriesgado) | **+13.0%** |
| Mercados / día | media 21.5, mediana 23 (de ~96 posibles) |
| % días con PnL > 0 | 73% (n=112 días) |
| Profit factor | 1.30 |
| EV total acumulado | +154 unidades de payoff |

## Lectura honesta

- El edge es **rentable en papel tras fees**: +13% ROI por apuesta, robusto (= modelo del veredicto oficial).
- Es **baja frecuencia / baja exposición**: ~21 apuestas/día, capital chico por apuesta (~0.51 unidades).
- **Consistente**: 73% de días positivos, profit factor 1.30, no errático.

## Lo que NO reportamos (y por qué) — decisión 2026-06-02

Se decidió (Pedro) reportar **solo métricas por-apuesta bien definidas**, y NO inventar un bankroll. Por lo tanto se EXCLUYEN:

| Métrica omitida | Por qué |
|-----------------|---------|
| **Sharpe / Sortino anualizados** | Calcularlos requiere bankroll y serie de retornos; anualizar ×√252 sobre 112 días infla artificialmente (un cálculo previo dio "7.2", engañoso — el diario era 0.455). Se deja para Exp3 con capital definido. |
| **Max drawdown %** | Sin bankroll, el % sobre capital no está bien definido (en unidades de PnL fue −7.6 sobre +154 ≈ −4.9%, pero el % real depende del sizing). |
| **Kelly / sizing** | PROJECT_DESIGN lo deja como "Nivel 2, otro proyecto". Es Exp3. |

## Caveats (heredados del veredicto)

1. **Capacity NO modelada.** El +13% asume comprar a `pm_up_price_open` con spread fijo 1%. A tamaño real, el order book (mercados de 15m son chicos) movería el precio y reduciría el edge. **El rendimiento solo es realista a capital mínimo.** Medir capacity = Exp3.
2. **Sin latencia ni slippage por tamaño.** Asume ejecución instantánea al precio de apertura.
3. **Periodo ~4 meses** → posible régimen único.
4. **Forward (Exp1, may-jun) confirmado a 67% con D bien calculado, pero n=118** (CI ancho).

## Para Exp3 (dimensionamiento real)
- Empezar con **capital mínimo viable** (a ese tamaño, capacity no es problema → las métricas de arriba ~aplican).
- Luego: capacity test con order book, Kelly fraccional para sizing, Sharpe/Sortino/DD con bankroll real, walk-forward mes a mes, latencia+slippage simulados.
