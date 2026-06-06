> # ⛔ CORRECCIÓN (2026-06-02) — ESTE REPORTE ESTABA EQUIVOCADO
>
> Este reporte le decía a Exp1 "tu D está mal calculado, usá el método de Exp2 (60-67%)". **Era al revés.** El agente de Exp1 detectó que **el método de Exp2 tenía lookahead bias**: calculaba D con trades de DURANTE la ventana `[ts_open, ts_close)` en vez de ANTES `[ts_open−15min, ts_open)`.
>
> **Verificado:** el D predictivo correcto da **~48% (no significativo)** — NO hay edge. El 60-67% de Exp2 era artefacto de medición concurrente. **Exp1 calculaba D correctamente (predictivo, ~51%) todo el tiempo.**
>
> **Acción para Exp1:** NO adoptar el método de Exp2 como "el correcto". Tu cálculo predictivo era el bueno. Lo único válido del método de abajo es la **fórmula** Black-76 (mejora sobre el delta del ticker), PERO **aplicada a trades ANTES de ts_open**, nunca durante la ventana. Si recomputás D con Black-76, mantené tu ventana predictiva `[ts_open−Xm, ts_open)`.
>
> El resto de abajo se conserva solo como registro.

---

# (INVALIDADO) REPORTE PARA EL AGENTE DE Exp1 — Calcular D con el método de Exp2 (en paralelo)

**De:** Exp2 (`D:\EXPERIMENTOS BTC OPTIONS\`) — replicación histórica de la señal D.
**Para:** el agente de Exp1 (`D:\openclaw\PROJECT DESIGN\`) — logger live.
**Fecha:** 2026-06-02.
**Asunto:** agregar un segundo cálculo de D (método Black-76 de Exp2) EN PARALELO al actual, sin tocar el tuyo.

---

## 1. Por qué te escribo (el hallazgo)

Exp2 replicó tu experimento con datos históricos (backfill Deribit + Polymarket, dic-2025→abr-2026). Resultado: la señal **D_15m_otm_dotm** con `|D|>5` predice el outcome de los mercados BTC Up/Down 15m con **accuracy 60.7%** (n=2.408, p<1e-4), EV neto positivo tras costos. Edge validado.

Pero al comparar con tu logger, encontramos una discrepancia grande: **tu Exp1 mide ~51% sobre el mismo tipo de señal.** Investigamos si era (A) cambio de régimen o (B) diferencia de cálculo. El test fue concluyente:

> Tomamos TUS outcomes (de tu DB) y recalculamos D con NUESTRO método (Black-76) sobre los trades de Deribit de TU período (may-jun 2026). Resultado: **accuracy 66.95%** (n=118), no 51%.
> Y al comparar tu `D_15m_otm_dotm` guardado vs nuestro D recalculado por ventana: **correlación −0.016, coincidencia de signo 53.6%.** Son señales casi NO relacionadas.

**Conclusión: el edge SÍ existe y SÍ generaliza a tu período. La diferencia 51% vs 67% es por CÓMO se calcula D, no por el mercado.** Algo en el cálculo/recolección de D de tu logger lo está degradando.

## 2. Lo que te pido

**NO cambies tu cálculo actual de D.** Mantenelo tal cual (para no romper tu pre-registro v1.0.0 ni tu serie histórica). En su lugar:

> **Agregá, en paralelo, un SEGUNDO conjunto de columnas D calculadas con el método de Exp2 (Black-76), sobre los MISMOS trades que ya capturás.**

Así, cada ventana tendrá tu D original **y** el D-método-Exp2. Podés comparar ambos en vivo y ver cuál predice mejor, sin perder nada.

Sugerencia de nombres de columnas nuevas (no pisar las tuyas):
`D_5m_otm_dotm_bs76`, `D_10m_otm_dotm_bs76`, `D_15m_otm_dotm_bs76`, `D_*_atm_bs76`, `V_*_bs76`, `n_trades_*_bs76`.

## 3. El método EXACTO de Exp2 (copiable)

Para cada trade de opción que ya capturás (necesitás: `timestamp`, `instrument_name`, `direction`, `amount`, `iv`, `index_price`):

### Paso 1 — Filtro de IV
Descartar el trade si `iv <= 0` o `iv > 300` (en %). Son <0.5%, datos corruptos.

### Paso 2 — Recomputar delta con Black-76 (NO usar el delta directo de Deribit)
```python
import math
def norm_cdf(x): return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def black76_delta(F, K, T, sigma, is_call):
    # F = index_price del trade ; K = strike (del instrument_name)
    # T = (expiry - timestamp_trade) en años, ACT/365 ; sigma = iv/100 ; r = 0
    if sigma <= 0 or T <= 0 or F <= 0 or K <= 0:
        return None
    d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    delta = norm_cdf(d1) if is_call else norm_cdf(d1) - 1.0
    return round(delta, 6)
```
- `K`, tipo (C/P) y expiry se parsean del `instrument_name` (ej. `BTC-26JUN26-60000-P` → K=60000, P, expiry=26JUN26 a las 08:00 UTC).
- **Validación que hicimos:** este Black-76 reproduce el `mark_price` de Deribit con error mediano 0.0005 → el delta es fiel.

### Paso 3 — Clasificar moneyness por |delta| (cortes del paper Alexander 2022)
```python
def moneyness_bucket(delta_abs):
    if 0.02 < delta_abs <= 0.125: return "otm_dotm"   # DOTM
    if 0.125 < delta_abs <= 0.375: return "otm_dotm"  # OTM
    if 0.375 < delta_abs <= 0.625: return "atm"
    return None  # IGNORED (deep-OTM ruido o ITM) -> el trade NO entra en la señal
```

### Paso 4 — Presión firmada y agregación
```python
sign = +1.0 if direction == "buy" else -1.0   # taker buyer=+1, seller=-1
signed_pressure = sign * amount * abs(delta)
```
Por ventana de 15 min y por bucket (`otm_dotm` / `atm`), separando call/put:
```
A_C = sum(signed_pressure de calls) ; A_P = sum(signed_pressure de puts)
D = (A_C - A_P) / 2
V = (A_C + A_P) / 2
```
Variantes temporales: para `D_5m` usar solo trades de los últimos 5 min antes del cierre; `D_10m` últimos 10; `D_15m` los 15 (toda la ventana). Misma fórmula, distinta ventana de trades.

## 4. Diferencias probables con tu cálculo actual (qué revisar en tu logger)

La correlación −0.016 sugiere que tu D difiere en algo estructural. Candidatos a auditar en tu `src/deribit_feed.py` / `signal.py`:
1. **Delta**: ¿usás el delta directo del ticker de Deribit (que es el de AHORA, no el del momento del trade)? Eso introduce error/lookahead. Black-76 lo computa al instante del trade.
2. **Moneyness**: ¿tus cortes de |delta| son los mismos (0.02/0.125/0.375/0.625)? ¿clasificás bien DOTM+OTM como `otm_dotm`?
3. **Trades perdidos**: ¿tu WebSocket se reconecta y pierde trades? Un D sobre trades incompletos se degrada. Compará tu `n_trades_15m` contra el de un backfill de `history.deribit.com` para la misma ventana.
4. **Dirección**: ¿`buy`/`sell` mapea a +1/−1 sobre el lado TAKER? Si está invertido o mal asignado, D se rompe.

## 5. Cómo validar que quedó bien

Una vez agregues el D-bs76 en paralelo:
- En cada ventana, compará `sign(D_15m_otm_dotm)` (tuyo) vs `sign(D_15m_otm_dotm_bs76)` (nuevo). Si coinciden ~100%, calculabas bien y el problema era otro. Si coinciden ~50% (como nos pasó), tu D estaba roto y el bs76 es el bueno.
- Cuando juntes ~100+ ventanas con `|D_bs76|>5`, mirá la accuracy de `D_bs76` vs outcome. Esperamos ~60%.

## 6. Reglas (heredadas, no negociables)
- READ-ONLY sobre Deribit/Polymarket. Registra, no opera.
- NO modifiques tu pre-registro v1.0.0 ni tu D original — esto es ADITIVO.
- El D-bs76 es exploratorio en tu experimento hasta que acumules muestra propia.
- Fuente de trades histórica si la necesitás: **`history.deribit.com`** (NO `www.deribit.com`, que solo retiene ~1 día).

## 7. Resumen en una frase
Tu señal D parece estar mal calculada (no correlaciona con el método validado). Agregá en paralelo el D-Black-76 de Exp2 (código arriba), compará en vivo, y deberías ver subir la accuracy de ~51% hacia ~60%.
