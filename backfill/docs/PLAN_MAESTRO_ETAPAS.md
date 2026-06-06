---
doc_id: PLAN_MAESTRO_ETAPAS
rol: protocolo
estado: vivo (mapa unico de etapas)
fase: transicion a datos finos (Exp4)
version: 1.0
creado: 2026-06-03
uso: EL plan unico por etapas, de punta a punta. Donde estamos, que sigue, en que orden. Leer junto con ESTADO_PROYECTO.
---

# PLAN MAESTRO POR ETAPAS — de datos gruesos a datos finos

> Este es el mapa único. Cada etapa tiene: objetivo, entregable, criterio de cierre. Los planes detallados (PLAN_DATOS_TICK, PLAN_ORDERBOOK_SPREAD, PLAN_BUSQUEDA_EDGE) son el "cómo" de cada etapa.

## RESUMEN DE DÓNDE ESTAMOS

- **Exp2 (datos gruesos): CERRADO.** ~28 hipótesis probadas con velas BTC 1min + precio contrato medio. Resultado: **NO hay edge predictivo** (mercado eficiente). La señal D de opciones refutada. Cada "edge" aparente (60/56/80/58/85%) cayó: lookahead, índice contaminado, tautología, precio pegajoso.
- **Diagnóstico:** nuestros datos eran demasiado GRUESOS para ver lo que los bots explotan (ellos usan tick + velocidad).
- **Exp4 (datos FINOS): CERRADO (2026-06-03).** Re-adquiridos datos tick (20,47M ticks a 0,1s, Mar–Abr 2026) + orderbook con **ask ejecutable real**. Re-test de todas las hipótesis finas → **NO hay edge de TOMADOR**: el precio es eficiente/calibrado; cada edge aparente era precio no-ejecutable; con el ask real, EV<0. Detalle: [HALLAZGOS_DATOS_FINOS.md](HALLAZGOS_DATOS_FINOS.md).
- **AHORA (Exp5, frontera no explorada): el lado MAKER.** Todo lo anterior fue del lado tomador (pagar ask). La pregunta abierta de "cómo ganan los bots 24/7": ¿una estrategia maker (postear límites, cobrar el spread ≈3,5pp) es rentable tras selección adversa? Tenemos los datos para **estudiarlo** (orderbook 866M + outcomes); READ-ONLY → medir, no operar.

---

## ETAPA 0 — Cierre formal de Exp2 (datos gruesos)
- **Objetivo:** dejar documentado que Exp2 (predicción con datos gruesos) está cerrado, con el aprendizaje.
- **Entregable:** ESTADO_PROYECTO actualizado + lista de las ~28 hipótesis y las 5 trampas.
- **Estado:** 🟡 parcial (documentado en piezas; falta consolidar).
- **Cierre:** un doc o sección que liste todo lo refutado (para no repetirlo).

## ETAPA 1 — Adquisición de datos finos  ← **SIGUIENTE**
Plan detallado: [PLAN_DATOS_TICK.md](PLAN_DATOS_TICK.md)
- **1A — Ticks Polymarket** (PRIORIDAD 1): 1 escaneo DuckDB, ~minutos, ~20.5M ticks limpios (filtrar 4.9% basura timestamp<2023). Trae: trade real (precio ejecutable, side, size) + spot BTC en ms.
  - Entregable: `data/raw/pm_ticks.parquet` + hash. Criterio: ~20M filas, período dic25-abr26, sin basura.
- **1B — Orderbook (muestra)** (PRIORIDAD 2): [PLAN_ORDERBOOK_SPREAD.md](PLAN_ORDERBOOK_SPREAD.md). Solo muestra (~10-15 días), 1 escaneo. Para spread/ask real + capacity.
  - Entregable: `data/raw/orderbook_sample/` + tabla de spread estratificado.
- **1C — Futuros BTC** (PRIORIDAD 3, decisión Pedro): Binance perpetuo, para lead-lag futuros→spot.
  - Entregable: `data/raw/binance_futures.parquet`. (Opcional, solo si se persigue lead-lag.)
- **Cierre Etapa 1:** datos finos en disco, limpios, con hashes, granularidad verificada (ms).

## ETAPA 2 — Construcción de features finos
- **Objetivo:** de los ticks crudos, construir las series limpias y ordenadas.
- **Entregables:**
  - `spot_fine.parquet` — spot BTC en ms (extraído de ticks).
  - `contract_trades.parquet` — trades del contrato (precio ejecutable, side, size, t_seconds).
  - Recomputar la trayectoria del contrato a resolución real (no medio cada 10s).
- **Cierre:** features con test anti-lookahead (cada feature usa solo info < momento de decisión).

## ETAPA 3 — Re-test de hipótesis con datos finos
Plan detallado: [PLAN_BUSQUEDA_EDGE.md](PLAN_BUSQUEDA_EDGE.md) (actualizado a datos finos)
Las hipótesis que con datos gruesos NO pudimos evaluar:
- **H-fino-1:** momentum BTC en SEGUNDOS → ¿predice mov del contrato? (antes: velas 1min muy gruesas)
- **H-fino-2:** lead-lag futuros→spot→Polymarket (requiere 1C)
- **H-fino-3:** flujo de órdenes del contrato — ¿los humanos compran contra el momentum? (mecanismo contrarian; usa side+size de ticks)
- **H-fino-4:** EV con precio EJECUTABLE real (ask de 1B), no medio
- **H-fino-5:** capacity — ¿cuánto tamaño aguanta? (sizes de 1B)
- **Reglas:** anti-lookahead estricto, train→holdout FRESCO sellado, validar candidatos en vírgenes (ETH/SOL).
- **Cierre:** cada hipótesis con veredicto (edge / no edge), trampas verificadas.

## ETAPA 4 — Validación de candidato (si aparece)
- **Objetivo:** si alguna hipótesis da edge en train, validarlo sin auto-engaño.
- **Pasos:** (1) backtest con costos REALES (ask+fee), (2) holdout sellado UNA vez, (3) datos vírgenes (ETH/SOL o forward Exp1), (4) capacity.
- **Cierre:** edge confirmado (procede Exp5/paper trading) o refutado (documentar).

## ETAPA 5 — Decisión final
- Si hay edge real y operable → diseñar paper trading (Exp5), con la advertencia de que competir requiere infra de velocidad.
- Si no → cierre definitivo: el edge de estos mercados es ejecución/MM (no análisis), requiere infra HFT, fuera de alcance.

---

## ORDEN DE EJECUCIÓN (la secuencia)
```
[AHORA] Etapa 1A: bajar ticks PM (minutos)
   -> 1B: muestra orderbook (spread)
   -> 1C: futuros (si Pedro decide lead-lag)
Etapa 2: construir features finos
Etapa 3: re-test hipotesis finas (train)
Etapa 4: validar candidato (holdout + virgenes) SI aparece
Etapa 5: decision (paper trading o cierre)
```

## REGLAS DURAS (de todo el proyecto, reforzadas)
1. Anti-lookahead estricto — verificar timestamp de CADA fuente (2 lookaheads cometidos por no hacerlo).
2. Precio EJECUTABLE (ask real), nunca el medio.
3. Holdout sellado, no re-usar (el de BTC ya se gastó → sellar uno fresco con datos finos).
4. Validar candidatos en vírgenes antes de creer.
5. Determinismo: hash por artefacto.
6. READ-ONLY, registra-no-opera (PROJECT_DESIGN §0).

## QUÉ FALTA DECIDIR (Pedro)
- ¿Incluir futuros (1C) desde el inicio, o solo spot fino primero?
- ¿Período/universo: las 3.835 ventanas con ticks, o filtrar más?
- ¿Sellar qué % de holdout fresco para la validación final?
