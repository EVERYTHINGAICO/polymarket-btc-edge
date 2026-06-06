---
doc_id: PRE_REGISTRO_v2.0.0
rol: pre-registro
estado: BORRADOR — sin firmar (se congela en EXP2-7)
fase: EXP2-7
version: 2.0.0 (draft)
creado: 2026-06-01
actualizado: 2026-06-01
uso: documento que Pedro firma ANTES de correr gates; congela hipótesis y parámetros (anti-cherry-picking)
---

# PRE-REGISTRO v2.0.0 — Exp2 (PLANTILLA SIN FIRMAR)

> **ESTADO: BORRADOR — NO FIRMADO.** Este documento se completa y firma en **Fase E**, DESPUÉS de tener el backfill en formato canónico y ANTES de correr los gates. Firmarlo congela la hipótesis (anti-cherry-picking). Una vez firmado, los valores se copian a `analysis_config.json` v2.0.0 y NO se cambian sin bump de versión + entrada en `_changelog`.

## Decisiones que Pedro debe fijar (rellenar en Fase E)

| Decisión | Valor (a definir) | Notas |
|----------|-------------------|-------|
| Variante D pre-registrada | `D_15m_otm_dotm` **o** `D_5m_otm_dotm` | Exp1 usó `D_15m`; la preliminar favoreció `D_5m`. Elegir UNA. |
| Umbral `\|D\|` | `> 5.0` (Exp1) o reconsiderar | El handoff notó que el umbral binario es cuestionable; si se cambia, justificar aquí. |
| Periodo histórico del backfill | `____` a `____` (UTC) | Más periodo = más poder, más riesgo de regime change. |
| Periodo de holdout sellado | **30% más reciente por fecha** (≈ abril 2026; el 70/30 de Exp1 pero TEMPORAL, no aleatorio) — DECIDIDO 2026-06-01 | NO se toca hasta corrida confirmatoria (EXP2-8). |
| `min_n_for_verdict` | `1000` (Exp1) o `____` | Antes de n, veredicto = `WAIT_FOR_MORE_DATA`. |
| Filtros heredados | `outcome∈{Up,Down}`, `is_incomplete=0`, `n_trades_15m ≥ 30` | Confirmar o ajustar. |

## Blindaje metodológico (de [AUDITORIA_PROTOCOLO.md](AUDITORIA_PROTOCOLO.md) — congelar ANTES de descargar)

Estos parámetros son grados de libertad que mueven D/accuracy. Se fijan a priori para evitar cherry-picking encubierto:

| Bloque | Parámetro | Valor a congelar | Estado |
|--------|-----------|------------------|--------|
| **split** | método + ratio | **temporal**, **70% train / 30% holdout** (sellado, el más reciente). Ratio = el de Exp1; temporal = mejora anti-leakage. Aleatorio solo secundario comparativo | DECIDIDO |
| **black_scholes** | modelo / IV / r / τ / S / redondeo | Black-76 / `iv` del trade / 0 / ACT/365 / `index_price` / 6 dec | a confirmar |
| **black_scholes** | sensibilidad | verificar veredicto estable con `r ∈ {0, 0.02}` | — |
| **moneyness** | cortes \|delta\| (de Exp1) | DOTM (0.02,0.125] · OTM (0.125,0.375] · ATM (0.375,0.625] · resto IGNORED | confirmado vs código Exp1 |
| **iv_filtro** | IV válida | descartar `iv ≤ 0` o `iv > 300%` (<0.5%, datos corruptos) + reporte n excluidos + sensibilidad tope ∈ {250,300,400} | confirmado empíricamente |
| **delta** | fuente | **recomputado Black-76** (histórico no trae delta); validado vs mark_price Deribit (err mediano 0.0005) | confirmado |
| **min_n_efectivo** | por gate | n que entra al test tras filtros (sug. ≥384) | a fijar |
| **robustness** | block bootstrap | n_resamples, seed, block_size; veredicto exige binomtest **y** bootstrap | a fijar |

## Gates a aplicar (idénticos a Exp1 salvo la variante elegida)

Gate 1 (D vs moneda), Gate 2 (D vs mercado indeciso `[0.45,0.55]`), Gate 3 (lead/lag, requiere trayectoria), Gate 4a (offset base), Gate 4b (costos: fee 0.07, spread 0.01, EV mín 0.005). Ver [`PLAN_EXP2.md`](PLAN_EXP2.md) §2.

Bonferroni: `n_tests_total = 5` → `α_corrected = 0.01` (si se prueban variantes extra confirmatorias, subir N y documentar).

## Firma

- [ ] Pedro confirma que NO ha mirado los resultados de gates sobre el holdout.
- [ ] Valores arriba copiados a `analysis_config.json` v2.0.0.
- [ ] `frozen_at_utc` + `frozen_by` registrados.

Firmado por: __________  Fecha UTC: __________
