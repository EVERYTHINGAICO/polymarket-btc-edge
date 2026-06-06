# REPORTE COMPLETO — PROYECTO DESIGN (Exp1 + Exp2)

**Fecha**: 2026-06-03
**Autor**: Compilación rigurosa de TODO lo investigado, probado, refutado y descubierto.
**Estado**: snapshot integral. Sin omisiones.

> Este documento consolida absolutamente todo el trabajo: hipótesis, experimentos, datos, código, paths, resultados, retractaciones, conclusiones, y caminos no explorados. Su propósito es servir como base para decidir si hay otra forma de atacar el problema usando matemáticas / física / microestructura, o si se cierra el proyecto.

---

## 0. RESUMEN EJECUTIVO

### Pregunta original
*¿Existe edge predictivo en el flujo de opciones BTC de Deribit para anticipar el outcome de mercados Polymarket BTC Up/Down 15min?*

### Veredicto consolidado al 2026-06-03

**NO hay edge predictivo confirmado.** Todas las hipótesis testeadas terminan en una de tres situaciones:
1. **Refutadas con datos vírgenes**: D opciones (Exp1: 51%, Exp2 corregido: 47.96%), momentum spot (anti-lookahead: 49–53%), reversión PM.
2. **Aparente edge desapareció al corregir lookahead bias**: el "60.7%" de Exp2 y el "55.6%" momentum eran ambos artefactos de usar información concurrente con la ventana.
3. **Edge nominal sí, pero comido por costos reales**: incluso cuando la accuracy parece positiva con info del primer minuto intra-ventana (versión "B" de momentum: 56.55%), Polymarket precia el contrato en <60s → EV neto cercano a cero o negativo a umbrales altos.

### El hallazgo positivo más interesante (no edge, sí información)
**El mercado Polymarket BTC 15m es eficiente y está calibrado**: `precio ≈ P(outcome)` en el grueso 0.3–0.7. Cualquier "edge" para taker es ilusión cuando se usa el ask realmente ejecutable. La única **frontera no explorada** que podría tener edge es **estrategia maker (cobrar spread)**, posiblemente combinada con un modelo del oráculo Chainlink (que es lo que decide outcome y NO sigue puntualmente a Binance).

### Lecciones metodológicas críticas
1. **Lookahead bias se esconde en hábitos de programación**: tomar `close[ts_open]` parece anti-lookahead pero la vela `[ts_open, ts_open+60s)` cierra a `+59s` (info posterior).
2. **Pre-registrar antes de mirar holdout** o el holdout se "gasta" con 26 hipótesis (problema de comparaciones múltiples).
3. **Replicación independiente** (datos vírgenes, otro asset, forward live) es el único método honesto de descartar suerte estadística.
4. **El precio del contrato Polymarket se ajusta en <60s** → cualquier edge teórico requiere baja latencia o ser maker.

---

## 1. TOPOLOGÍA DE PROYECTOS Y PATHS

### 1.1 Proyectos físicos en disco

| Path | Rol | Estado |
|------|-----|--------|
| `D:\descargas al dico vergas\PROJECT DESIGN\` | Copia base / autoridad histórica | NO contiene runtime actual; backup informativo |
| `D:\openclaw\PROJECT DESIGN\` | **Exp1 — copia activa, logger live** | Activo. Logger continuo capturando. |
| `D:\EXPERIMENTOS BTC OPTIONS\` | **Exp2 — backfill histórico dic-2025→abr-2026** | Cerrado: análisis exhaustivo con 26+ hipótesis. |

### 1.2 Documentos de autoridad

| Archivo | Path | Rol |
|---------|------|-----|
| `PROJECT_DESIGN.md` | `D:\openclaw\PROJECT DESIGN\PROJECT_DESIGN.md` | Autoridad — define el experimento, §0 reglas duras, §3 schema, §7.B gates |
| `CLAUDE.md` | Ambos proyectos | Instrucciones para agentes IA |
| `AGENTS.md` | Ambos proyectos | Topología y reglas operativas |
| `analysis_config.json` (Exp1) | `D:\openclaw\PROJECT DESIGN\analysis_config.json` | Pre-registro v1.0.0 FROZEN (2026-05-30T00:00Z) |
| `analysis_config.json` (Exp2) | `D:\EXPERIMENTOS BTC OPTIONS\analysis_config.json` | Pre-registro v2.0.0 FIRMADO (2026-06-02T08:07Z) |
| `analysis_config_v2.0.0_SIGNED_20260602T080755Z.json` | `D:\EXPERIMENTOS BTC OPTIONS\` | Copia timestamped para evidencia |

### 1.3 Plans, handoffs e historiales

**Exp1 (`D:\openclaw\PROJECT DESIGN\`):**
- `HANDOFF_2026-05-27.md` — primer outcome real
- `HANDOFF_2026-05-28.md` — logger continuo operativo
- `HANDOFF_2026-05-30.md` — análisis determinista listo (5 gates + hash)
- `HANDOFF_2026-06-01.md` — estado n=453
- `HANDOFF_FINAL_2026-05-27.md` — cierre G6.1
- `OPENCLAW_HANDOFF.md`, `OPENCLAW_PROMPT.md`, `OPENCLAW_RUNBOOK.md` — sistema de tareas controlado
- `MISION_OPENCLAW_PROJECT_DESIGN.md` — misión consolidada

**Exp2 (`D:\EXPERIMENTOS BTC OPTIONS\`):**
- `HANDOFF_EXP2_2026-05-31.md` — folder vacío + decisión inicial
- `HANDOFF_EXP2_2026-06-01.md` — re-framing meta=ganar dinero
- `HANDOFF_EXP2_2026-06-02.md` — backfill completo, gates corridos
- `REPORTE_PARA_EXP1_calculo_D.md` — alerta sobre D (luego refutada por sí mismos)
- `REPORTE_PARA_EXP1_validar_momentum.md` — pide validación independiente de momentum
- `docs/` — 22 documentos técnicos completos (ver §1.5)

### 1.4 Plan maestro persistente

`C:\Users\User\.claude\plans\esto-es-algo-de-delightful-clarke.md` — plan detallado de TODO lo que se hizo, incluyendo análisis Harvard de decisiones, evaluaciones tipo caso, y trayectoria completa de hipótesis evaluadas.

### 1.5 Documentación técnica de Exp2 (22 archivos en `docs/`)

| Archivo | Path | Contenido |
|---------|------|-----------|
| `README.md` | `docs/README.md` | Índice de documentos |
| `PLAN_EXP2.md` | `docs/PLAN_EXP2.md` | Qué hace Exp2 |
| `PLAN_MAESTRO_EJECUCION.md` | `docs/PLAN_MAESTRO_EJECUCION.md` | Cómo se ejecuta |
| `PLAN_MAESTRO_ETAPAS.md` | `docs/PLAN_MAESTRO_ETAPAS.md` | Etapas EXP2-1 hasta EXP2-8 |
| `DECISION_FUENTES.md` | `docs/DECISION_FUENTES.md` | Por qué se eligieron las fuentes primarias |
| `FUENTES_DATOS.md` | `docs/FUENTES_DATOS.md` | Columnas reales por fuente |
| `FUENTES_SECUNDARIAS.md` | `docs/FUENTES_SECUNDARIAS.md` | Tardis, otras fuentes (no usadas en V1) |
| `SCHEMA_CANONICO.md` | `docs/SCHEMA_CANONICO.md` | Estructura de DB |
| `PRE_REGISTRO_v2.0.0.md` | `docs/PRE_REGISTRO_v2.0.0.md` | Pre-registro con criterios fijos |
| `AUDITORIA_DATOS_vs_PLAN.md` | `docs/AUDITORIA_DATOS_vs_PLAN.md` | Diferencias con Exp1 documentadas |
| `AUDITORIA_PROTOCOLO.md` | `docs/AUDITORIA_PROTOCOLO.md` | 6 grados de libertad congelados |
| `ESTADO_PROYECTO.md` | `docs/ESTADO_PROYECTO.md` | **Foto viva** del estado (más reciente) |
| `ESTUDIO_MOMENTUM.md` | `docs/ESTUDIO_MOMENTUM.md` | Estudio del momentum (luego refutado por lookahead) |
| `EXPERIMENTO_FUTURO_MICROESTRUCTURA.md` | `docs/EXPERIMENTO_FUTURO_MICROESTRUCTURA.md` | Plan de Exp3 (microestructura + ML) |
| `HALLAZGOS_DATOS_FINOS.md` | `docs/HALLAZGOS_DATOS_FINOS.md` | Resultados tick-by-tick + orderbook |
| `METRICAS_RENDIMIENTO.md` | `docs/METRICAS_RENDIMIENTO.md` | Sharpe, drawdown, etc. |
| `PLAN_BUSQUEDA_EDGE.md` | `docs/PLAN_BUSQUEDA_EDGE.md` | Plan de búsqueda exhaustiva |
| `PLAN_DATOS_TICK.md` | `docs/PLAN_DATOS_TICK.md` | Plan para datos tick-level |
| `PLAN_ORDERBOOK_SPREAD.md` | `docs/PLAN_ORDERBOOK_SPREAD.md` | Plan para spreads de orderbook |
| `PROTOCOLO_BUSQUEDA_EDGE_ESTADISTICO.md` | `docs/PROTOCOLO_BUSQUEDA_EDGE_ESTADISTICO.md` | Protocolo Bonferroni, hold-out |
| `PROTOCOLO_FASES.md` | `docs/PROTOCOLO_FASES.md` | Protocolo de fases |
| `COMPARACION_EXP1_EXP2.md` | `docs/COMPARACION_EXP1_EXP2.md` | Comparativa de los dos experimentos |

---

## 2. FUNDAMENTO TEÓRICO

### 2.1 Paper base

**Alexander, C., Deng, J., Feng, J., & Wan, H. (2022).** *Net Buying Pressure and the Information in Bitcoin Option Trades*. **arXiv:2109.02776v2.**

**Tesis del paper:**
- Existe información direccional en el flujo de opciones de BTC.
- La señal vive principalmente en opciones **OTM y DOTM** (no ATM).
- Se degrada en ~1 hora.
- **Advertencia explícita del paper**: el desbalance crudo predice *volatilidad* claramente pero *dirección* solo débilmente.

**Construcción de la señal direccional D:**
```
D = (presión_compras_calls − presión_compras_puts) / 2
donde presión = direction_sign × amount × |delta|
direction_sign = +1 si taker buyer, -1 si taker seller
```

### 2.2 Mecanismo de resolución de Polymarket BTC Up/Down 15min

- Ventanas alineadas a UTC :00, :15, :30, :45.
- `outcome` = "Up" si `BTC_price[ts_close] >= BTC_price[ts_open]` según oráculo, "Down" en caso contrario.
- **Oráculo de resolución**: Chainlink BTC/USD en Polygon mainnet (`0xc907E116054Ad103354f2D350FD2514433D57F6f`).
- Chainlink NO es snapshot puntual: es **mediana de N nodos**, cada uno con su propio TWAP/VWAP de Coinbase, Binance, Kraken, etc., con updates por deviation threshold o heartbeat.
- Esto introduce un **lag estructural**: lo que paga Polymarket en `ts_close` representa un precio agregado de los últimos segundos/minutos.

### 2.3 Implicaciones operativas

| Punto | Detalle |
|-------|---------|
| Read-only | El proyecto NO opera, NO firma, NO usa wallets. Solo registra. PROJECT_DESIGN §0. |
| Stack | Python 3.11+, SQLite, asyncio, websockets, APIs públicas. PROJECT_DESIGN §2. |
| Fee taker Polymarket | ~1.8% sobre cost (Pedro asumió 1.8%; cap en 0.5 USD por share). |
| Order min size | $5 (verificado en investigación operativa). |
| Capacity típica | $400-500 max por market — vencen rápido y son chicos. |

---

## 3. HIPÓTESIS PROBADAS (CRONOLÓGICO + VEREDICTO)

### H1 — Señal D direccional (pre-registro v1.0.0 de Exp1)
- **Hipótesis**: D_15m_otm_dotm con `|D|>5` predice outcome de la ventana siguiente.
- **Variante exacta**: 15 minutos previos a `ts_open`, OTM+DOTM, threshold 5 absoluto.
- **Pre-registrado**: `analysis_config.json` v1.0.0 (Exp1), FROZEN 2026-05-30T00:00:00Z.
- **Resultado Exp1 live (n=587 al 2026-06-03)**: **51% accuracy** con |D|>5.
- **Resultado Exp2 backfill predictivo (dic-2025→abr-2026, n=7806)**: **47.96%** full / **46.12%** holdout.
- **Veredicto**: **NO_EDGE_FIN** en Exp2 corregido. Exp1 aún no llegó a n=1000 pero apunta al mismo veredicto.
- **Files**: `src/analysis/gates.py:gate1_d_vs_coin`, `reports/phases/fase_8_D_predictivo_*.json` (Exp2).

### H2 — Variantes de D (5m/10m/15m × OTM_DOTM/ATM)
- **6 variantes** comparadas: D_{5,10,15}m_{otm_dotm,atm}.
- **Resultado Exp1 (n=587)**:
  - D_5m_otm_dotm: 54.93% sin filtro / 48.72% con |D|>5
  - D_10m_otm_dotm: 51.10% / 48.78%
  - D_15m_otm_dotm: 50.12% / 50.86%
  - D_5m_atm: 47.98% / 45.00%
  - D_10m_atm: 51.25% / 54.55%
  - D_15m_atm: 51.11% / 51.26%
- **Patrón observado**: variantes cortas OTM/DOTM tienen ligeramente más accuracy sin filtro, **consistente con el paper** (degradación en ~1h). Pero ninguna supera 55% de forma robusta.
- **Veredicto**: **EXPLORATORIO** (no se puede cambiar pre-registro). Documentado en `src/analysis/exploratory.py:analyze_d_variants_accuracy`.

### H3 — Last-tick risk / FLIPs Chainlink vs Polymarket
- **Observación**: ~6% de ventanas en Exp1 tienen `sign(chainlink_close - price_to_beat) ≠ outcome`. En esas FLIPs, el movimiento mediano de BTC es $12 (vs $67 en estables).
- **Hipótesis**: ventanas tranquilas (poco movimiento) las decide ruido microstructural del último segundo / oracle pinning.
- **Resultado**: D accuracy ~54% en estables vs ~47% en flippy (gap ~7pp).
- **Veredicto**: **OBSERVACIÓN EXPLORATORIA** — sugiere que filtrar por volatilidad mínima podría mejorar accuracy, pero introducir ese filtro post-hoc es cherry-picking.
- **Files**: `src/analysis/exploratory.py:analyze_chainlink_vs_polymarket_flips`.

### H4 — Brackets de magnitud de D (sweet spot no monotónico)
- **Hipótesis**: ¿accuracy crece monotónicamente con |D|?
- **Resultado**: NO. En Exp1 (n=358):
  - `|D|∈[0,2)`: ~50%
  - `|D|∈[2,5)`: ~52%
  - `|D|∈[5,10)`: ~55% — sweet spot
  - `|D|∈[10,20)`: 48.6%
  - `|D|∈[20,100)`: 52%
  - `|D|∈[100,∞)`: 33% (n=3)
- **Veredicto**: El umbral `|D|>5` es **arbitrario** y la relación no es monotónica. Sugiere ruido más que señal estable.
- **Files**: `src/analysis/exploratory.py:analyze_d_brackets`.

### H5 — Lead-lag (D adelanta o es contemporáneo)
- **Hipótesis** (PROJECT_DESIGN §7.B Gate 3): ¿D predice ANTES de que se mueva pm_up_price?
- **Métrica**: mediana del `t_move` (cuándo pm_up_price se mueve >0.05 desde open).
- **Resultado Exp1**: mediana **30 segundos**.
- **Veredicto**: 30s es muy rápido — apenas viable operativamente con latencia humana, imposible si fee de orden tarda más.
- **Files**: `src/analysis/gates.py:gate3_lead_lag`.

### H6 — 26 hipótesis exploratorias en Exp2 sobre el holdout

Pedro de Exp2 probó **~26 hipótesis** sobre los mismos datos holdout. Pedro mismo lo dice: "Gasté el holdout" — esto implica **problema serio de comparaciones múltiples** (con 26 tests, ~1.3 dan p<0.05 por azar).

Categorías:
- **B (Polymarket pm_up_price intra-window momentum/reversion)** — `scripts/explore_edge_candidates.py`, `scripts/test_candidate_B_reversion_60_60_holdout.py`
- **V (D/V relation with realized volatility)** — diagnóstico, no edge directo
- **Momentum lookback múltiples** — `scripts/scan_momentum_lookbacks_costed.py`
- **Reversión en t=60s** — testeada y reportada (`reports/phases/candidate_B_reversion_60_60_holdout.json`)
- **Order flow / orderbook imbalance** — `scripts/scan_orderbook_imbalance_i1.py`
- **Market making (cobrar spread)** — `scripts/scan_market_making_m1.py`
- **Arbitrage orderbook** — `scripts/scan_orderbook_arbitrage_s1.py`

**Veredicto**: ninguna sobrevivió validación rigurosa con costos reales. Detalle en `docs/HALLAZGOS_DATOS_FINOS.md`.

### H7 — Momentum spot Binance (la que parecía la mejor)
- **Hipótesis**: `momentum = BTC[ts_open] - BTC[ts_open - 300s]` → bet Up si momentum > 0, Down si < 0, sin umbral.
- **Reportado por Pedro (lookahead)**: holdout 54.21% (n=2769), train 53.62% (n=6432).
- **Mi replicación de su número exacto (LOOKAHEAD)**: 54.25% (n=2767).
- **MI replicación CORREGIDA (anti-lookahead)**:
  - Exp2 holdout: **49.26%** — peor que moneda
  - Exp1 live (n=587): **53.41%** — apenas sobre azar, p_bonferroni*26 = 1.0
- **Causa del bias**: usar `close[ts_open]` toma el close de la vela `[ts_open, ts_open+60s)` = info de ~59s POSTERIORES.
- **Veredicto**: **REFUTADO**. El edge nominal era 100% lookahead bias.
- **Files**: `scripts/audit_momentum_signal.py` (Exp2 auto-auditó), `reports/phases/momentum_audit_report.md`, `reports/phases/momentum_lookback_*.csv`.

### H8 — Momentum con entrada 60s tarde (la que el usuario me pidió hoy)
- **Hipótesis A**: misma señal anti-lookahead, entrar 60s tarde (pm_up_price ya disponible a t=60s).
- **Hipótesis B**: usar señal hasta close de `[ts_open, ts_open+60s)` (info disponible al entrar a t+60s).
- **Resultado Exp1 (n=649)**:
  - **A**: accuracy 52.23%, EV +$0.024/apuesta (p=0.14, no significativo, total PnL +$15.82)
  - **B**: accuracy 56.55%, EV +$0.009/apuesta (p_bonf*26 = 0.0125, total PnL +$5.89)
- **Hallazgo crucial**: B tiene 4pp más accuracy pero **6 cents más caro el contrato** (Polymarket ya se ajustó al momentum en 60s). El extra accuracy se come en el extra cost.
- **Por umbral en B**: a |mom|>=$50 EV se hunde a NEGATIVO -$0.003 (market overshoot).
- **Veredicto**: **REFUTADO** — el mercado precia el momentum en <60s eficientemente. La accuracy nominal es real pero el EV neto no.

### H9 — Black-76 delta vs Deribit ticker delta (lookahead en el delta)
- **Hipótesis** (inicialmente sospechada): el logger live de Exp1 usa el `delta` reportado por Deribit (cacheado 30s), no el delta calculado al instante del trade con Black-76.
- **Pedro afirmó**: correlación −0.016 entre D_live vs D_bs76, signo 53.6%.
- **MI verificación con 518 ventanas Exp1 backfilleadas con Black-76 (`scripts/backfill_bs76_from_history.py`)**:
  - Correlación Pearson: **0.997** (no -0.016)
  - Coincidencia de signo: **96.7%** (no 53.6%)
  - n_trades casi idéntico: live mean 95.1 vs bs76 mean 95.2
- **Veredicto**: **REFUTADO** — el logger live de Exp1 está bien. La discrepancia que reportó Pedro fue por su propio bug de lookahead en su pipeline (luego confirmado y corregido por Pedro mismo el 2026-06-02). El logger de Exp1 es correcto.
- **Files**: `src/signal_bs76.py`, `tests/test_signal_bs76.py` (29/29 PASS), `scripts/backfill_bs76_from_history.py`, `scripts/migrate_add_bs76_columns.py`.

### H10 — Mercado eficiente con orderbook real (Pedro 2026-06-03)
- **Hipótesis**: existe edge para taker en alguna asimetría de orderbook.
- **Test exhaustivo con 20.47M ticks a 0.1s + 866M filas de orderbook**:
  - Comprar al favorito: **EV −3.2%**
  - Fade de extremos (favorite-longshot): **−6.0% con ASK REAL** (parecía +13.4% con precio sintético)
  - Lag/latencia: refutado (el contrato lidera al spot)
  - Order flow: 52.35% (< break-even)
- **Veredicto**: **NO HAY EDGE DE TAKER**. El precio es eficiente y está calibrado (precio ≈ P(outcome) en 0.3–0.7). Detalle: `docs/HALLAZGOS_DATOS_FINOS.md`.
- **Conclusión más importante**: cada "edge" aparente era precio NO ejecutable (mid o último negociado). Con el ask real → negativo.

### H11 — Market making (cobrar spread como MAKER) [NO EXPLORADO A FONDO]
- **Hipótesis**: si el mercado es eficiente para taker, ¿hay edge para maker?
- **Razonamiento**: los bots que precian eficientemente cobran el spread (~3.5pp). Eso ES dinero, si sobrevivís la selección adversa (te quedan colgadas las apuestas que los otros NO querían).
- **Estado**: scripts existen (`scripts/scan_market_making_m1.py`, `scripts/scan_market_making_m1_samples.py`), pre-registro existe (`reports/phases/m1_rule_001_preregistration.md`), holdout verdict existe (`reports/phases/m1_rule_001_holdout_verdict.md`).
- **Veredicto**: **PARCIALMENTE EXPLORADO**. Reportes en `reports/phases/m1_*` están listos. Requiere lectura completa para decidir si es edge real o también es ilusión.
- **NOTA**: este es el camino **menos refutado** del proyecto al día de hoy.

---

## 4. EXPERIMENTOS REALIZADOS (CÓDIGO + DATA)

### 4.1 Exp1 — Logger live (en curso)

#### Captura de datos
- **`src/continuous_logger.py`** — loop principal, 4 threads (Deribit WS persistente + scheduler + intrawindow sampler + outcome resolver). Comando: `py -m src.logger --continuous --with-trajectory --db data/observations.db --log-path reports/live/continuous_logger.log`
- **`src/deribit_feed.py`** — WS stream + REST clients, delta resolver con cache 30s
- **`src/polymarket_feed.py`** — descubrir markets, fetch midpoint, resolver outcome con retries
- **`src/chainlink_feed.py`** — leer precio BTC/USD del oráculo Polygon (con fallback de 4 RPCs)
- **`src/signal.py`** — D/V rolling buffer, thread-safe
- **`src/intrawindow_sampler.py`** — sampler de pm_up_price (segundo-a-segundo durante primeros 120s, luego cada 30s)
- **`src/raw_trade_logger.py`** — captura paralela de trades con iv + index_price para Black-76
- **`src/db.py`** — schema, helpers, WAL mode
- **`src/forward_market_data.py`** — captura de candidatos forward (Exp1 fase 7)

#### Análisis
- **`src/analysis/config.py`** — carga inmutable de pre-registro
- **`src/analysis/data.py`** — load + hash input
- **`src/analysis/stats.py`** — binomtest, Bonferroni, K-fold determinista
- **`src/analysis/gates.py`** — 5 gates oficiales (Gate 1, 2, 3, 4a, 4b)
- **`src/analysis/verdict.py`** — consolidación + hash output
- **`src/analysis/exploratory.py`** — sub-análisis (NO afectan veredicto): FLIPs, d_variants, brackets, pm_open brackets, running accuracy
- **`src/analysis/forward_rules.py`** — reglas para Fase 7 forward

#### Scripts adicionales
- **`scripts/run_analysis.py`** — CLI determinista (corre los 5 gates + exploratorios)
- **`scripts/backfill_bs76_from_history.py`** — backfill de D-Black76 desde `history.deribit.com`
- **`scripts/migrate_add_bs76_columns.py`** — ALTER TABLE additive
- **`scripts/window_id_audit.py`** — auditoría de window IDs
- **`scripts/one_window_pilot.py`** — piloto de una ventana
- **`scripts/live_t1_deribit_capture.py`**, **`scripts/live_t3_time_alignment.py`**, **`scripts/live_t4_resilience_check.py`** — tests de Fase 1/3/4
- **`scripts/run_continuous_collection.py`** — wrapper de captura continua
- **`scripts/monitor_collection.py`** — monitor de progreso

#### Tests
- **`tests/test_analysis_fixtures.py`** — 16 fixtures sintéticas (16/16 PASS)
- **`tests/test_signal.py`** — D/V calculation
- **`tests/test_signal_bs76.py`** — Black-76 (29/29 PASS)
- **`tests/test_db.py`**, `tests/test_logger.py`, `tests/test_deribit_feed.py`, etc.

### 4.2 Exp2 — Backfill histórico (cerrado)

#### Construcción del dataset
- **`scripts/init_db.py`** — crea `data/observations_exp2.db` (mirror de Exp1 + provenance)
- **`scripts/build_windows.py`** — extrae 9,231 ventanas BTC 15m del dataset HF `aliplayer1/polymarket-crypto-updown`
- **`scripts/build_outcomes.py`** — recupera 9,231/9,231 outcomes vía CLOB API
- **`scripts/build_deribit_trades.py`** — baja 1,491,915 trades de `history.deribit.com` (117 días)
- **`scripts/build_deribit_features.py`** — computa D variants con Black-76 (anti-lookahead, corregido 2026-06-02)
- **`scripts/build_polymarket_prices.py`** — pm_up_price_open + trajectory (880k ticks)
- **`scripts/build_chainlink_refs.py`** — chainlink_close + price_to_beat para 9,231 ventanas
- **`scripts/build_pm_ticks.py`** — ticks Polymarket (20.47M a 0.1s)
- **`scripts/build_orderbook_snapshots.py`** + **`build_orderbook_i1_samples.py`** + **`build_orderbook_m1_samples.py`** — orderbook snapshots (866M filas)
- **`scripts/download_orderbook_part0.py`** — descarga raw de orderbook
- **`scripts/merge_research_dataset.py`** — consolida en `data/processed/research_dataset_v1.parquet`
- **`scripts/load_to_db.py`** — pobla la DB

#### Exploración de hipótesis (las 26+)
- **`scripts/explore_edge_candidates.py`** — TRAIN-only exploration de hipótesis B (PM momentum/reversion) y V (volatility)
- **`scripts/test_candidate_B_reversion_60_60_holdout.py`** — test sellado del candidato B
- **`scripts/audit_momentum_signal.py`** — replica el momentum BTC y produce el audit report
- **`scripts/scan_momentum_lookbacks_costed.py`** — barre lookbacks de momentum con costos
- **`scripts/scan_orderbook_imbalance_i1.py`** — scan de imbalance del orderbook
- **`scripts/scan_orderbook_arbitrage_s1.py`** — scan de arbitraje
- **`scripts/scan_market_making_m1.py`** — scan de market making
- **`scripts/scan_market_making_m1_samples.py`** — versión con samples
- **`scripts/pilot_orderbook_arbitrage_s1.py`** — piloto de arbitraje s1
- **`scripts/probe_orderflow.py`** — investigación de order flow
- **`scripts/study_maker.py`** — estudio dedicado a market making
- **`scripts/test_regime_vs_calc.py`** — test que originalmente diagnosticó (mal) que Exp1 tenía bug de cálculo

#### Análisis (clonado de Exp1)
- **`src/analysis/`** — idéntico a Exp1 + `analysis_config.json` v2.0.0
- **`scripts/run_analysis.py`**, **`scripts/run_analysis_exp2.py`** — orquestadores
- **`src/signal.py`** — D/V
- **`src/data_sources/sources_config.py`** — endpoints de fuentes

#### Tests
- **`tests/test_analysis_fixtures.py`** — 16/16 PASS
- **`tests/test_bootstrap.py`** — block bootstrap
- **`tests/test_no_lookahead.py`** — 3/3 PASS (incluye chequeo de que D usa solo trades pre-`ts_open` ahora)

---

## 5. INVENTARIO DE DATOS

### 5.1 Exp1 — DB `data/observations.db` (SQLite WAL)

**Tabla `observations`** (39 columnas tras migración bs76):
```
window_id, ts_open, price_to_beat, pm_up_price_open, deribit_index_open,
D_5m_otm_dotm, D_10m_otm_dotm, D_15m_otm_dotm, D_5m_atm, D_10m_atm, D_15m_atm,
V_5m_otm_dotm, V_10m_otm_dotm, V_15m_otm_dotm,
n_trades_5m, n_trades_10m, n_trades_15m,
ts_close, deribit_index_close, chainlink_close, outcome, pm_up_price_close,
is_incomplete, insufficient_flow, notes,
-- columnas bs76 agregadas 2026-06-02 --
D_5m_otm_dotm_bs76, D_10m_otm_dotm_bs76, D_15m_otm_dotm_bs76,
D_5m_atm_bs76, D_10m_atm_bs76, D_15m_atm_bs76,
V_5m_otm_dotm_bs76, V_10m_otm_dotm_bs76, V_15m_otm_dotm_bs76,
n_trades_5m_bs76, n_trades_10m_bs76, n_trades_15m_bs76,
bs76_computed_at_utc, bs76_source
```

**Tabla `observations_intrawindow`**: `(window_id, t_seconds, pm_up_price, sampled_at_utc)`. Sampleo: cada segundo 0-120s, después cada 30s.

**Tabla `deribit_trades_raw`** (nueva 2026-06-02): trades crudos para recomputar Black-76.

**Estado al 2026-06-03**:
- Total ventanas: 587 con outcome (subiendo ~4/h)
- Con D_bs76: 519
- Trades raw: 56,542

### 5.2 Exp2 — Datasets parquet (`D:\EXPERIMENTOS BTC OPTIONS\data\`)

**Raw**:
- `raw/polymarket_markets_btc15m.parquet` — 9,231 ventanas (dataset HF `aliplayer1/polymarket-crypto-updown`, revision `ba1ad37c…`, hash determinista `6110d928…`)
- `raw/deribit/*.jsonl` — 117 días de trades, 1,491,915 totales
- `raw/binance_btc_1m.jsonl` — 168,000 candles de BTC/USDT 1m
- `raw/orderbook/btc15m_orderbook_part0.parquet` — orderbook raw

**Interim**:
- `interim/outcomes.parquet` — 9,231/9,231 resolved via CLOB
- `interim/pm_open.parquet` — pm_up_price al ts_open
- `interim/pm_trajectory.parquet` — 880,587 ticks intra-window
- `interim/chainlink_refs.parquet` — 9,231 con chainlink_close + price_to_beat
- `interim/deribit_features.parquet` — D variants computadas (corregidas 2026-06-02)
- `interim/orderbook_btc15m_snapshots.parquet` — snapshots orderbook
- `interim/_train_explore.parquet` — exploración train

**Processed**:
- `processed/research_dataset_v1.parquet` — dataset consolidado, hash `f1d06bcb…`, 9,225 obs con TODO completo. **Esta es la fuente de verdad para Exp2.**

**Invalidated**:
- `invalidated_lookahead_20260602/deribit_features_lookahead.parquet` — D antigua con lookahead bias
- `invalidated_lookahead_20260602/research_dataset_v1_lookahead.parquet` — dataset antiguo invalidado
- `invalidated_lookahead_20260602/reports_phases/*` — reportes que dieron veredicto inválido

**Cache HF**: `.hf_cache_orderbook/` — cache local

**DB local Exp2** (mencionada en docs): `data/observations_exp2.db` — populated, mirror de Exp1. Si la querés inspeccionar es la misma estructura.

### 5.3 Reportes — Exp2 `reports/phases/`

**Análisis principal**:
- `fase_8_D_predictivo_full.json` — D corregido, sin lookahead, sobre todo el dataset (NO_EDGE_FIN)
- `fase_8_D_predictivo_holdout.json` — D sobre holdout (WAIT_FOR_MORE_DATA por n<1000)

**Momentum**:
- `momentum_audit_report.json` + `.md` — reproducción del 54.21% de Pedro
- `momentum_lookback_*.csv` y `.json` — barridos de lookback con/sin costos
- `momentum_lookback_costed_verdict.md` — veredicto

**Reversión (candidato B)**:
- `candidate_B_reversion_60_60_holdout.json` — test sellado
- `train_edge_scan_B_entry_to_resolution.csv` + `train_edge_scan_B_pm_trajectory.csv`

**Orderbook imbalance (i1)**:
- `i1_orderbook_imbalance_scan_train_*.csv` y `.json` — scans
- `i1_orderbook_imbalance_train_summary.md` — resumen

**Market making (m1)**:
- `m1_market_making_scan_*.csv` y `.json` — scans
- `m1_rule_001_preregistration.md` — pre-registro
- `m1_rule_001_holdout_verdict.md` — veredicto

**Arbitrage (s1)**:
- `s1_pilot_arb_runs_spread_100.csv`
- `s1_pilot_interpretation_spread_100.md`
- `s1_pilot_paired_snapshots_spread_100.csv`
- `s1_pilot_report_spread_100.json`

**Volatility (V)**:
- `train_edge_scan_V_volatility.csv`

**Orderbook**:
- `fase_D_orderbook_snapshots_summary.md`

### 5.4 Reportes — Exp1 `reports/phases/`

- `fase_2_audit.md` ... `fase_7_audit.md` — auditorías por fase
- `fase_6_real_window_pass_report.md` — primer outcome real
- `fase_6_one_window_pilot_report.md` — piloto exitoso
- `fase_7_preliminary_analysis_2026-05-30.json` — n=218
- `fase_7_preliminary_2026-06-01.json` — n=358
- `fase_7_preliminary_2026-06-02_0907.json` — n=506
- `fase_7_forward_collection_started_2026-06-03.md` — arranque de Fase 7 forward
- `fase_7_forward_rules_freeze_2026-06-03.md` — reglas congeladas

---

## 6. ESTADO ACTUAL Y CONCLUSIONES

### 6.1 Lo refutado (con evidencia)
| Hipótesis | Refutación |
|-----------|------------|
| D opciones predice outcome | Exp1 live 51% / Exp2 corregido 47.96%. NO_EDGE_FIN. |
| Momentum spot Binance predice | Lookahead bias. Real anti-lookahead: 49–53%. |
| D_5m_otm_dotm "mejor variante" | Exploratorio, sin significancia genuina tras Bonferroni. |
| Reversión PM intra-window | Candidate B holdout: marginalmente positivo, no replica forward. |
| Orderbook imbalance taker | Scan completo: ningún imbalance da EV positivo neto. |
| Arbitrage taker | s1 pilot: no edge sostenible. |

### 6.2 Lo NO refutado / abierto
| Hipótesis | Estado |
|-----------|--------|
| **Market making (m1)** | Pre-registro y holdout verdict existen. Requieren lectura focal antes de declarar. |
| **Modelado de Chainlink** | Nadie ha probado a modelar el agregador. Es la clave de la resolución. |
| **Microestructura sub-segundo** | Plan documentado en `docs/EXPERIMENTO_FUTURO_MICROESTRUCTURA.md`. |
| **Bot order flow detection** | Detectar bots que arbitran y operar antes / como contraparte. |

### 6.3 Lo que SÍ aprendimos (resultados positivos del proyecto)
1. **El mercado Polymarket BTC 15m es EFICIENTE para taker.** Esto ES un resultado científico válido.
2. **El paper Alexander 2022 fue confirmado en su tesis modesta**: señal direccional débil, presente pero no operativa con costos típicos.
3. **El logger live de Exp1 captura D correctamente** (correlación 0.997 con Black-76 anti-lookahead). El bug que parecía haber, no era bug.
4. **Pre-registro + Bonferroni + holdout sellado funcionan**: detectaron el lookahead bias del momentum cuando los datos vírgenes no replicaron.
5. **Chainlink no sigue a Binance puntualmente** — es agregador. Eso desconecta "qué hace BTC" de "qué decide Polymarket".

### 6.4 Logger live al 2026-06-03 (snapshot operativo)
- Corriendo desde 2026-05-28T02:56Z (~7 días)
- 587 ventanas con outcome resuelto
- ETA a 1000: ~5 días más
- Cuando llegue a 1000, corrida final dará probable **NO_EDGE_FIN** (proyección lineal).
- D_bs76 backfill listo, columnas en DB.

---

## 7. CAMINOS NO EXPLORADOS / IDEAS NUEVAS PARA "DECIFRAR EL MERCADO"

### 7.1 Sub-experimento Market Making (Exp3 candidato más fuerte)
**Tesis**: si los bots arbitrans los taker, ellos cobran el spread. Vos podés cobrarlo también si colocás límites y aceptas selección adversa.

**Riesgos a modelar**:
- Selección adversa (te quedan las apuestas que los otros no querían).
- Inventario asimétrico (acumular un lado).
- Cancellation rates / fill rates.

**Data disponible**:
- 866M filas de orderbook
- 20.47M ticks 0.1s
- 9,225 ventanas completas

**Scripts ya escritos**:
- `scripts/scan_market_making_m1.py`, `scripts/study_maker.py`
- Pre-registro: `reports/phases/m1_rule_001_preregistration.md`
- Verdict: `reports/phases/m1_rule_001_holdout_verdict.md` ← **LEER ESTO ANTES DE DECIDIR**

### 7.2 Modelado de Chainlink (camino sin explorar)
**Tesis**: el outcome lo decide Chainlink, no Binance. Si modelás qué precio Chainlink va a publicar, predecís outcome aunque Binance haga otra cosa.

**Componentes del modelo**:
1. Identificar los N nodos del feed Chainlink BTC/USD (es público on-chain).
2. Cada nodo TWAPea M segundos de Coinbase/Binance/Kraken/etc.
3. Mediana on-chain de los nodos.
4. Heartbeat / deviation threshold para nuevos updates.

**Lo que esto te daría**:
- Predecir el precio Chainlink en `ts_close` con info de spot multi-exchange.
- Comparar con el precio de Polymarket → ver si hay gap consistente.
- Si Polymarket precia por Binance pero Chainlink usa Coinbase con USDT/USD off-par → hay edge estructural.

**Por qué nadie lo hizo**: requiere ingeniería significativa (RPC histórico Polygon, identificar nodos, replicar lógica de agregación) y solo vale la pena si el gap es lo suficientemente grande para superar fees.

### 7.3 Detección y modelado de bots arbitradores
**Tesis**: si hay bots que arbitran en <60s (lo que sospechamos por la eficiencia observada), su flujo es identificable en orderbook y ticks.

**Pasos**:
1. Identificar firmas de bots en `pm_trajectory.parquet`: trades muy rápidos, sizes consistentes, timing post-eventos de spot.
2. Operar **como contraparte de bots tontos** o **antes que bots lentos**.
3. Requiere alta frecuencia → puede no ser viable sin latencia profesional.

### 7.4 Asimetría buy-sell en orderbook (no testeada exhaustivamente)
**Tesis**: el orderbook tiene asimetría que predice movimiento de corto plazo (microestructura clásica). Si la asimetría se ajusta en <X segundos, podés operar en esa ventana.

**Data**: `interim/orderbook_btc15m_snapshots.parquet`
**Scripts existentes**: `scripts/scan_orderbook_imbalance_i1.py` — pero solo desde lado taker.
**Pregunta abierta**: ¿hay edge si usás imbalance + maker?

### 7.5 Modelo físico de difusión + reversión (PROBABLEMENTE OVERKILL)
**Tesis**: el precio del contrato es un proceso estocástico observable. Modelos físicos (ej. Ornstein-Uhlenbeck con drift, reflective barriers en 0 y 1) podrían dar mejor predicción de short-term price evolution.

**Pros**:
- Marco matemático elegante.
- Si BTC tiene microestructura mean-reverting en 5m (lo cual se observa), el contrato también.

**Contras**:
- Si Polymarket ya es eficiente, este modelo no agrega info — solo formaliza lo que el mercado ya sabe.
- Riesgo de overfit con muchos parámetros.

### 7.6 Datos externos (no usados en V1)
- **Tardis**: ticks/orderbook profundo de Deribit y otros (documentado en `docs/FUENTES_SECUNDARIAS.md`).
- **Coinbase Direct Market Data**: si Chainlink usa Coinbase, esto sería más relevante que Binance.
- **Trade-level Polymarket on-chain**: hay datos en Polygon de cada match. Hasta ahora se usaron CLOB y dataset HF.

### 7.7 Combinatoria de features con ML (Exp3 microestructura)
**Documentado en**: `docs/EXPERIMENTO_FUTURO_MICROESTRUCTURA.md`
**Idea**: tomar las decenas de features que tenemos (D, V, n_trades, pm_trajectory, orderbook depth, ask/bid moves, etc.) y entrenar un modelo (XGBoost/LightGBM con cuidado anti-lookahead) sobre el target binary.

**Riesgos**:
- Sobreajuste masivo si no se hace con disciplina (pre-registro de features, hold-out estricto, cross-validation temporal).
- "Edge" puede ser memorización del régimen específico.

---

## 8. LECCIONES METODOLÓGICAS

### 8.1 Lookahead bias se esconde donde menos lo esperás
- **Caso 1**: el `close[ts_open]` de Binance kline parece "el precio en ts_open" pero es el precio al final del minuto = lookahead de 59s.
- **Caso 2**: tomar trades en `[ts_open, ts_close)` para computar D te parece "concurrente" pero es lookahead porque cuando apostás aún no han pasado.
- **Defensa**: tests automáticos que verifican que ningún input tiene timestamp ≥ ts_open. `tests/test_no_lookahead.py` (Exp2) ahora lo hace.

### 8.2 Multiple comparisons devora p-values
- 26 hipótesis sobre el mismo holdout → ~1.3 dan p<0.05 por suerte.
- Bonferroni × N es necesario, pero no suficiente si las hipótesis fueron generadas mirando los datos.
- **Defensa**: pre-registro firmado ANTES de tocar holdout.

### 8.3 Replicación en datos vírgenes es el único veredicto creíble
- Lo único que distingue "edge real" de "suerte estadística".
- Datos vírgenes admisibles: otro periodo temporal, otro asset, otra fuente.
- **Cuidado**: el "holdout" se gasta. Una vez que viste los outcomes, está contaminado.

### 8.4 Edge nominal en accuracy ≠ edge en EV
- Mostrado en H8: la versión B tiene 4pp más accuracy pero EV peor.
- El mercado precia tu edge antes de que apuestes.
- **Métrica que importa**: EV neto de costos, Sharpe, drawdown.

### 8.5 Determinismo bit-exact paga
- Hash SHA256 de input + output. Mismo input → mismo output_hash siempre.
- Permite verificar regresiones, auditar runs, reproducir resultados.
- Tanto Exp1 como Exp2 implementan esto.

### 8.6 Pre-registro es disciplina aplicada al futuro-yo
- El "yo de mañana" va a querer ajustar umbrales viendo los datos. Pre-registro lo prohíbe.
- Sin pre-registro, cualquier ajuste post-hoc invalida la conclusión.

---

## 9. PREGUNTAS QUE QUEDAN ABIERTAS

1. **¿Cuántos segundos exactos tarda Polymarket en pricear el momentum?** (H8 mostró que <60s, pero ¿es 5s? ¿30s? La estructura óptima de entrada depende de esto.)

2. **¿La estrategia maker (m1) realmente es rentable o también es ilusión?** Leer `reports/phases/m1_rule_001_holdout_verdict.md`.

3. **¿Modelar Chainlink directamente da edge?** Nadie lo intentó. La hipótesis es: si Binance ≠ Chainlink, el gap es explotable.

4. **¿Hay edge en ETH/SOL del mismo dataset HF?** Pedro nunca los miró → datos vírgenes. Si momentum o algo análogo funciona ahí, el descarte de BTC podría haber sido prematuro.

5. **¿Las FLIPs Chainlink-Polymarket (6%) son operativas?** Si pudieras predecir cuándo va a haber FLIP (ventana tranquila + posición Polymarket clara), podrías apostar EN CONTRA del consenso.

6. **¿Hay otros mercados Polymarket con mecánica similar (e.g., hourly BTC, daily)?** El mismo análisis aplicado ahí podría dar otra señal.

7. **¿Bonereaper conoce alguna pieza que no hayamos visto?** Sus comentarios sobre Chainlink agregador + USDT/USD off-par sugieren conocimiento operativo que vale la pena pelearle.

---

## 10. APÉNDICE — INVENTARIO COMPLETO DE ARCHIVOS

### 10.1 Exp1 — TODOS los archivos clave

**Raíz**:
```
D:\openclaw\PROJECT DESIGN\PROJECT_DESIGN.md     ← autoridad
D:\openclaw\PROJECT DESIGN\analysis_config.json  ← pre-registro v1.0.0 FROZEN
D:\openclaw\PROJECT DESIGN\config.json           ← config controlador
D:\openclaw\PROJECT DESIGN\config.py
D:\openclaw\PROJECT DESIGN\controller.py         ← controlador OpenClaw
D:\openclaw\PROJECT DESIGN\state.json
D:\openclaw\PROJECT DESIGN\forward_rules_config.json
D:\openclaw\PROJECT DESIGN\dashboard_sample.json
D:\openclaw\PROJECT DESIGN\requirements.txt
D:\openclaw\PROJECT DESIGN\README.md
```

**Handoffs y notas**:
```
HANDOFF_2026-05-27.md, HANDOFF_2026-05-28.md, HANDOFF_2026-05-30.md,
HANDOFF_2026-06-01.md, HANDOFF_FINAL_2026-05-27.md
AGENTS.md, CLAUDE.md
MISION_OPENCLAW_PROJECT_DESIGN.md
OPENCLAW_HANDOFF.md, OPENCLAW_PROMPT.md, OPENCLAW_RUNBOOK.md
OPENCLAW_PACKAGE_MANIFEST.md
```

**src/** (13 módulos):
```
src/__init__.py, src/chainlink_feed.py, src/continuous_logger.py, src/db.py,
src/deribit_feed.py, src/forward_market_data.py, src/intrawindow_sampler.py,
src/logger.py, src/polymarket_feed.py, src/raw_trade_logger.py, src/signal.py,
src/signal_bs76.py
```

**src/analysis/** (8 módulos):
```
src/analysis/__init__.py, config.py, data.py, exploratory.py, forward_rules.py,
gates.py, stats.py, verdict.py
```

**scripts/** (20 scripts):
```
scripts/autonomous_loop.py, scripts/backfill_bs76_from_history.py,
scripts/collect_forward_market_data.py, scripts/finalize_T7.py,
scripts/live_collection_supervisor.py, scripts/live_t1_deribit_capture.py,
scripts/live_t3_time_alignment.py, scripts/live_t4_resilience_check.py,
scripts/migrate_add_bs76_columns.py, scripts/monitor_collection.py,
scripts/one_window_pilot.py, scripts/project_controller.py, scripts/run_analysis.py,
scripts/run_collection_once.py, scripts/run_continuous_collection.py,
scripts/run_forward_rules.py, scripts/safe_task_executor.py,
scripts/stat_validate.py, scripts/validate_system.py, scripts/window_id_audit.py
```

**tests/** (15 archivos):
```
tests/test_analysis_fixtures.py, test_autonomous_loop.py, test_db.py,
test_deribit_feed.py, test_executor.py, test_forward_market_data.py,
test_forward_rules.py, test_goal_selector.py, test_logger.py,
test_polymarket_feed.py, test_project_controller.py, test_scaffold.py,
test_signal.py, test_signal_bs76.py, test_window_id_audit.py
```

**adapters/**, **approvals/**, **core/**, **notebooks/**, **prompts/**, **snapshots/**, **tasks/**: infraestructura del controlador OpenClaw.

**data/**:
```
D:\openclaw\PROJECT DESIGN\data\observations.db        ← SQLite live
D:\openclaw\PROJECT DESIGN\data\observations.db-shm    ← WAL shared mem
D:\openclaw\PROJECT DESIGN\data\observations.db-wal    ← WAL log
```

**reports/**:
```
reports/audits/, reports/cycles/, reports/live/, reports/phases/, reports/approvals/
```

### 10.2 Exp2 — TODOS los archivos clave

**Raíz**:
```
D:\EXPERIMENTOS BTC OPTIONS\analysis_config.json       ← v2.0.0 firmado
D:\EXPERIMENTOS BTC OPTIONS\analysis_config_v2.0.0_DRAFT.json
D:\EXPERIMENTOS BTC OPTIONS\analysis_config_v2.0.0_SIGNED_20260602T080755Z.json
D:\EXPERIMENTOS BTC OPTIONS\analysis_config_exp1_v1.0.0.json.backup
D:\EXPERIMENTOS BTC OPTIONS\CLAUDE.md
D:\EXPERIMENTOS BTC OPTIONS\HANDOFF_EXP2_2026-05-31.md
D:\EXPERIMENTOS BTC OPTIONS\HANDOFF_EXP2_2026-06-01.md
D:\EXPERIMENTOS BTC OPTIONS\HANDOFF_EXP2_2026-06-02.md
D:\EXPERIMENTOS BTC OPTIONS\REPORTE_PARA_EXP1_calculo_D.md
D:\EXPERIMENTOS BTC OPTIONS\REPORTE_PARA_EXP1_validar_momentum.md
```

**src/** (5 módulos + analysis):
```
src/__init__.py, src/signal.py
src/analysis/{__init__.py, config.py, data.py, exploratory.py, gates.py, stats.py, verdict.py}
src/data_sources/{__init__.py, sources_config.py}
src/features/__init__.py
```

**scripts/** (24 scripts):
```
scripts/audit_momentum_signal.py
scripts/build_chainlink_refs.py
scripts/build_deribit_features.py
scripts/build_deribit_trades.py
scripts/build_orderbook_i1_samples.py
scripts/build_orderbook_m1_samples.py
scripts/build_orderbook_snapshots.py
scripts/build_outcomes.py
scripts/build_pm_ticks.py
scripts/build_polymarket_prices.py
scripts/build_windows.py
scripts/download_orderbook_part0.py
scripts/explore_edge_candidates.py
scripts/init_db.py
scripts/load_to_db.py
scripts/merge_research_dataset.py
scripts/pilot_orderbook_arbitrage_s1.py
scripts/probe_orderflow.py
scripts/run_analysis.py
scripts/run_analysis_exp2.py
scripts/scan_market_making_m1.py
scripts/scan_market_making_m1_samples.py
scripts/scan_momentum_lookbacks_costed.py
scripts/scan_orderbook_arbitrage_s1.py
scripts/scan_orderbook_imbalance_i1.py
scripts/study_maker.py
scripts/test_candidate_B_reversion_60_60_holdout.py
scripts/test_regime_vs_calc.py
```

**docs/** (22 documentos — ver §1.5).

**tests/**:
```
tests/test_analysis_fixtures.py     ← 16/16 PASS
tests/test_bootstrap.py             ← block bootstrap
tests/test_no_lookahead.py          ← 3/3 PASS, ahora verifica que D no use ts_close
```

**data/**: ver §5.2 (raw, interim, processed, invalidated).

**reports/phases/**: 40+ archivos de resultados (CSV, JSON, MD).

### 10.3 Data del usuario `D:\descargas al dico vergas\PROJECT DESIGN\` (base/backup)
Es el repo original. Contiene snapshots históricos. NO se usa para runtime actual.

---

## 11. PRÓXIMOS PASOS POSIBLES

Te dejo opciones ordenadas por costo (esfuerzo) y por upside potencial:

### Opción A — Cerrar el proyecto con honestidad (mínimo esfuerzo)
1. Esperar Exp1 a n=1000 (~5 días).
2. Correr análisis final → probable NO_EDGE_FIN oficial.
3. Documentar el cierre. Publicar como "ejemplo de proyecto bien hecho que terminó refutando su hipótesis principal" — es resultado científico válido.

### Opción B — Profundizar en el camino menos refutado (medio esfuerzo)
1. Leer cuidadosamente `reports/phases/m1_rule_001_holdout_verdict.md` y `docs/HALLAZGOS_DATOS_FINOS.md`.
2. Si Market Making (m1) muestra señal real → diseñar Exp3 paper trading focalizado en maker.
3. Pre-registrar formalmente la estrategia maker.

### Opción C — Modelar Chainlink (alto esfuerzo, alto upside teórico)
1. Identificar nodos del feed Chainlink BTC/USD.
2. Reverse-engineer su lógica de agregación.
3. Construir modelo predictivo del precio Chainlink usando spot multi-exchange.
4. Comparar contra precio Polymarket → buscar gaps consistentes.
5. Requiere ~2-4 semanas de ingeniería.

### Opción D — Replicar momentum sobre ETH/SOL
1. Bajar dataset HF para ETH y SOL (mismo `aliplayer1`).
2. Aplicar EXACTAMENTE las hipótesis ya pre-registradas (D, momentum, etc.) sin tunear nada.
3. Si funcionan en alguno → indicio fuerte de que el descarte BTC fue prematuro y vale la pena más data.
4. Tiempo: ~1 día.

### Opción E — Aceptar que el mercado es eficiente y pivotar
1. La conclusión científica es clara: mercados Polymarket BTC 15m son eficientes para taker.
2. Pivotar a otro mercado / asset / mecánica con menos competencia.
3. Aprovechar la maquinaria construida (logger continuo, análisis determinista, anti-cherry-picking) para otro target.

---

**FIN DEL REPORTE**

Si querés profundizar en alguna sección, indicame cuál (e.g., "leeme el m1_rule_001_holdout_verdict y decime si hay algo ahí" o "modelemos Chainlink") y arranco.
