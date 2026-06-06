---
doc_id: PLAN_EXP2
rol: protocolo
estado: estable
fase: EXP2 (todas)
version: 1.0
creado: 2026-06-01
actualizado: 2026-06-01
uso: define QUÉ se calcula (señal D + 5 gates) y las fases del experimento
---

# PLAN EXP2 — Replicar la señal D con datos históricos

> **Estado:** plan de trabajo activo. Decidido por Pedro el 2026-06-01.
> **Una frase:** hacer *exactamente* lo que hizo Exp1 (señal direccional **D** → 5 gates → veredicto de edge), pero alimentando el pipeline con **datos históricos de backfill** (HuggingFace) en vez de recolección en vivo.
> **Lo nuevo (microestructura, orderbook, skew, IV, EV/backtest, ML) NO es parte de hoy.** Vive en [`EXPERIMENTO_FUTURO_MICROESTRUCTURA.md`](EXPERIMENTO_FUTURO_MICROESTRUCTURA.md) como Exp3 pendiente.

---

## 0. Qué NO cambia respecto a Exp1

La **pregunta de investigación**, el **método** y el **veredicto** son idénticos a Exp1 (PROJECT_DESIGN §7.B):

> ¿La señal direccional D, construida del order flow de opciones BTC de Deribit, predice el outcome de los mercados Polymarket "BTC Up/Down 15m" MEJOR que el precio que el propio mercado ya tiene?

Lo único que cambia es **de dónde salen los datos**: backfill histórico en vez de logger en vivo. Por eso se **reutiliza tal cual** el código analítico de Exp1 (`src/analysis/`), y solo se escribe nuevo el **pipeline de ingesta** que produce el mismo schema canónico.

## 1. La señal D (definición exacta, del código de Exp1 `src/signal.py`)

Por cada trade de opción clasificado:
```
signed_pressure = sign(direction) * amount * delta_abs
    sign = +1 si direction == "buyer", -1 si "seller"
```
Agregado dentro de una ventana temporal, separado por moneyness bucket (`otm_dotm` = {OTM, DOTM}; `atm` = ATM) y tipo (call/put):
```
A_C = Σ signed_pressure de calls
A_P = Σ signed_pressure de puts
D   = (A_C - A_P) / 2     ← señal direccional
V   = (A_C + A_P) / 2     ← señal de volumen/presión
```
**Variantes** = {ventana} × {bucket}: `D_5m_otm_dotm`, `D_10m_otm_dotm`, `D_15m_otm_dotm`, `D_5m_atm`, `D_10m_atm`, `D_15m_atm`, más `n_trades_Xm` y `V_Xm_otm_dotm`.

- **Variante pre-registrada en Exp1:** `D_15m_otm_dotm`, umbral `|D| > 5`.
- Las demás se computan pero solo se interpretan como **exploratorias**.

## 2. Los 5 gates (del código real `src/analysis/gates.py`)

Corren sobre el **holdout** (no train). Cada uno devuelve `AVANZA | FIN | INSUFICIENTE`.

| Gate | Pregunta | Métrica / criterio AVANZA |
|------|----------|---------------------------|
| **1 — D vs moneda** | Filtrando `\|D\| > umbral`, ¿`sign(D)` coincide con outcome >50%? | accuracy ≥ 0.55 **y** binomtest p < α_corregido |
| **2 — D vs mercado** | Cuando `pm_up_price_open ∈ [0.45,0.55]` (mercado indeciso) y `\|D\|` grande, ¿D acierta? | accuracy ≥ 0.55 **y** p < α_corregido |
| **3 — lead/lag** | ¿La señal aparece ANTES de que el precio del contrato se mueva? | mediana `t_move` ≥ 30s (requiere trayectoria intra-ventana) |
| **4a — base offset** | ¿El desfase Deribit-index ↔ Chainlink-close < movimiento típico de la ventana? | mediana(gap/move) < 1.0 |
| **4b — costos** | Backtest con spread+fees+slippage. ¿EV neto > 0? | EV neto por apuesta ≥ 0.005 |

**Veredicto global** (`verdict.py`): `EDGE_VALIDATED` si todos AVANZA; `NO_EDGE_FIN` si algún gate FIN; `WAIT_FOR_MORE_DATA` si n < min_n. Determinismo bit-exact: mismo DB + mismo config ⇒ mismo `output_hash`.

## 3. Schema canónico (lo que el backfill debe producir)

Ver [`SCHEMA_CANONICO.md`](SCHEMA_CANONICO.md). Tabla `observations`, una fila por ventana de 15m, columnas que los gates **exigen**:
`window_id, ts_open, ts_close, outcome, pm_up_price_open, deribit_index_open, chainlink_close, price_to_beat, n_trades_15m`, las 6 variantes `D_*`, las `V_*`. Tabla `trajectory` (intra-ventana `pm_up_price` vs `t_seconds`) **solo si el backfill lo permite** — si no, Gate 3 sale INSUFICIENTE (igual que en Exp1 hoy).

## 4. Fuentes de datos (del research del 2026-06-01)

Decididas y verificadas en [`DECISION_FUENTES.md`](DECISION_FUENTES.md) (caso Harvard) + [`FUENTES_DATOS.md`](FUENTES_DATOS.md) (columnas reales):
- **Polymarket (precios/ventanas):** HF `aliplayer1/polymarket-crypto-updown` (primaria; `BrockMisner` backup) → subsets `markets`, `prices`, `ticks`, `orderbook`, `spot_prices`. Filtrar `crypto=BTC`, `timeframe=15-minute`.
- **Outcome:** Polymarket **CLOB API** (`tokens[].winner`, autoridad). NO derivar del precio (flips de último segundo).
- **Deribit (order flow para D):** `BarendPotijk/deribit_historical_trades` vía API pública. Trae `direction`, `amount`, `iv`, `index_price`, `instrument_name` → call/put, amount, direction directos; **`delta` y `moneyness` se RECOMPUTAN** (Black-76 + cortes por |delta| del paper, ver [`AUDITORIA_PROTOCOLO.md`](AUDITORIA_PROTOCOLO.md)).
- **Spot BTC referencia:** Binance klines 1m (Gate 4a, vol).

## 5. Fases de ejecución (orden estricto — datos ANTES de hipótesis)

| Fase | Qué | Entregable | Regla dura |
|------|-----|-----------|------------|
| **A — Inventario** | Leer columnas reales de cada subset HF (sin bajar todo) | `FUENTES_DATOS.md` completo + confirmación de qué gates son posibles | No fijar umbrales todavía |
| **B — Schema** | Diseñar `observations` + `trajectory` + `backfill_provenance` | `SCHEMA_CANONICO.md` + `scripts/init_db.py` | Mirror del schema Exp1 |
| **C — Clonar análisis** | `robocopy` de `src/analysis/` + `tests/` desde Exp1 | módulos reusados verbatim | NO tocar Exp1 (read-only) |
| **D — Backfill determinista** | `scripts/backfill_data.py` calcula D de los trades Deribit + une con Polymarket | DB poblada + SHA256 impreso | `verify_backfill_determinism.py` = mismo hash 2x |
| **E — Pre-registro v2.0.0** | Pedro firma `analysis_config.json` v2.0.0 **antes** de correr gates | config FROZEN + `PRE_REGISTRO_v2.0.0.md` | Firmar ANTES de ver resultados |
| **F — Correr análisis** | `py scripts/run_analysis.py` sobre holdout | `reports/phases/fase_7_final_analysis_exp2.json` | Aceptar veredicto tal como caiga |
| **G — Comparar** | Veredicto Exp1 vs Exp2 | doc de comparación | — |

## 6. Reglas duras (heredadas de PROJECT_DESIGN §0)

- REGISTRA, no opera. Read-only sobre toda fuente. Sin trading/wallets/keys.
- Exp1 (`D:\openclaw\PROJECT DESIGN\`) es **referencia read-only** — no tocar, no detener su logger.
- **Pre-registro v2.0.0 se firma ANTES de mirar el backfill** (anti-cherry-picking).
- Si el periodo de backfill solapa con datos de Exp1 → declarar y considerar exclusión.
- Cambiar un umbral tras ver outcomes = p-hacking. Requiere bump de versión + `_changelog`.

## 7. Decisiones pendientes de Pedro (Fase E)

1. ¿Variante pre-registrada para Exp2 = `D_15m_otm_dotm` (igual a Exp1) o `D_5m_otm_dotm` (la que mostró más accuracy preliminar)?
2. Periodo histórico exacto del backfill (define poder estadístico vs riesgo de regime change).
3. Periodo de holdout temporal (últimos N meses, sellado hasta corrida final).
4. `min_n_for_verdict` (Exp1 = 1000).
