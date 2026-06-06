# HANDOFF — 2026-05-28

## Quién
Claude Code (sesión Pedro / contact@everythingaico.com).

## Misión completada
**Logger persistente en modo continuo, Opción C del plan.** PROJECT_DESIGN §9 cumplido. El sistema ahora puede correr `python -m src.logger --continuous` y capturar todas las ventanas de Polymarket alineadas al reloj UTC (96/día → ~1000 ventanas en ~10.5 días).

## Goals ejecutados

| Goal | Estado | Detalle |
|------|--------|---------|
| L-1 stream_deribit_trades | ✅ PASS | Función agregada a `src/deribit_feed.py`. `collect_live_deribit_trades` intacta. |
| L-2 Thread-safe RollingSignalBuffer | ✅ PASS | Lock en `add_trade`, `prune`, `trades_in_window`. |
| L-3 update_outcome helper | ✅ PASS | Update parcial en `src/db.py`. |
| L-4 ContinuousLogger | ✅ PASS | NUEVO `src/continuous_logger.py`. Clase con 4 threads. |
| L-5 CLI --continuous | ✅ PASS | Flag agregado a `src/logger.py`. |
| L-6 Smoke test | ⏸ IN PROGRESS | Logger corriendo en background, primera ventana abrió OK a las 03:00Z. Pendiente verificar 2-3 ventanas más. |

## Bug crítico resuelto: User-Agent / Cloudflare 403

**Síntoma:** primera corrida del logger continuo a las 00:00:05Z escribió `price_to_beat: null`. Diagnóstico inicial pensó que era network blip.

**Causa real:** `src/chainlink_feed.py` no incluía header `User-Agent`. Python urllib usa por default `Python-urllib/3.X` que Cloudflare clasifica como bot y devuelve 403 Forbidden en drpc.org y publicnode.com.

**Verificación reproducible (ejecutada en la sesión):**
```
Sin UA:   HTTPError: HTTP Error 403: Forbidden
Con UA Mozilla/5.0:   200 OK + precio Chainlink válido
```

**Fix aplicado:** agregado `'User-Agent': 'Mozilla/5.0'` al header de `_eth_call_with_diag()` en `src/chainlink_feed.py`.

**Por qué funcionó ayer (G-7 PASS con price_to_beat numérico):** suerte con la política anti-bot de Cloudflare. Hoy fueron más estrictos. La omisión del UA fue mi error de origen.

## Archivos creados/modificados (esta sesión)

### Modificados
- `src/deribit_feed.py` — agregada `stream_deribit_trades(on_trade, stop_event)` + función `_eth_call_with_diag` no, eso es chainlink. Solo stream_deribit_trades.
- `src/signal.py` — Lock en `RollingSignalBuffer`.
- `src/db.py` — helper `update_outcome`.
- `src/chainlink_feed.py` — `fetch_chainlink_btc_usd_close_fast` + `_eth_call_with_diag` + **User-Agent fix**.
- `src/logger.py` — flag `--continuous`.
- `CLAUDE.md` — append estado 2026-05-28.
- `AGENTS.md` — append cambios de sesión.

### Nuevos
- `src/continuous_logger.py` — clase `ContinuousLogger`.
- `scripts/run_continuous_collection.py` — wrapper alternativo (NO se usa con `--continuous` directo, queda como alternativa).
- `scripts/finalize_T7.py` — ya existía del 27, no cambió.
- `HANDOFF_2026-05-28.md` — este archivo.

### No tocados
- `PROJECT_DESIGN.md` — sin cambios (la única modificación previa fue Fase 6.b autorizada el 2026-05-27).
- `.env`, `data/` (manual), `controller.py`, `core/`, `adapters/`.
- `scripts/one_window_pilot.py` — sigue siendo válido para test de UNA ventana.

## Estado del logger corriendo

A las 03:07:17Z (cuando se generó este handoff parcial):

- Background ID: `b304ice01`
- Proceso vivo desde 02:56:29Z
- Primera ventana abrió 03:00:00Z (btc-updown-15m-1779937200) con `price_to_beat=$74,156.07` (G6.1b verificado ✓)
- Próximo boundary: 03:15:00Z
- Próxima validación crítica: ventana #2 a 03:15Z (debería tener buffer Deribit completo de 15 min)

## Comandos canónicos

### Detener el logger corriendo actualmente

```powershell
# Desde otra terminal:
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
```

O Ctrl+C en la terminal del logger si está accesible.

### Relanzar logger continuo

```powershell
cd "D:\openclaw\PROJECT DESIGN"
py -m src.logger --continuous --with-trajectory `
  --db "D:\openclaw\PROJECT DESIGN\data\observations.db" `
  --log-path "D:\openclaw\PROJECT DESIGN\reports\live\continuous_logger.log"
```

### Verificar estado durante recolección

```powershell
# stdout últimas 30 líneas
Get-Content "D:\openclaw\PROJECT DESIGN\reports\live\continuous_stdout.log" -Tail 30

# log JSON
Get-Content "D:\openclaw\PROJECT DESIGN\reports\live\continuous_logger.log" -Tail 20

# count filas en SQLite
py -c "import sqlite3; c = sqlite3.connect('D:/openclaw/PROJECT DESIGN/data/observations.db'); print(c.execute('SELECT COUNT(*) FROM observations WHERE window_id != \"demo-window\"').fetchone())"
```

### Test de UNA ventana (smoke)

```powershell
py -m src.logger --one-window-pilot --with-trajectory `
  --db "D:\openclaw\PROJECT DESIGN\data\observations.db" `
  --log-path "D:\openclaw\PROJECT DESIGN\reports\live\logger_runtime.log"
```

## Plan para llegar a 1000 ventanas (Fase 6)

1. **Detener** la corrida de validación actual cuando se vea ≥3 ventanas consecutivas con outcome resuelto.
2. **Limpiar SQLite opcionalmente**: las primeras ventanas pueden ser descartadas si tienen `n_trades_15m` bajo (buffer incompleto al arranque).
3. **Relanzar el logger** ≥20 min antes del boundary `:00 / :15 / :30 / :45` que se quiera contar como #1 de la serie de 1000.
4. **Dejar correr ~10.5 días** (96 ventanas/día × ~10.5 = 1008).
5. **Monitor periódico**:
   - Tail del log JSON cada N horas.
   - Count de SQLite (`SELECT COUNT(*) WHERE is_incomplete=0`).
   - Alertar si `chainlink_open_failed` o `gamma_unresolved` aparecen seguidos.

## Riesgos abiertos

| Riesgo | Mitigación |
|--------|------------|
| T4 (resilience caída de red/luz) WAIVED | Aceptado. Si pasa caída, las ventanas afectadas quedarán con `insufficient_flow=1`. |
| RPC públicos de Polygon cambian política | Paralelización + UA Mozilla. Si todos los 4 fallan, `chainlink_open_failed` evento explícito en log. |
| Gamma latencia >30 min para resolución | Logger marca como `gamma_unresolved_after_30min`, fila sigue válida para análisis sin outcome. |
| Primera ventana después de arranque tiene buffer Deribit incompleto | Documentado. Para corrida limpia, arrancar 20 min antes del primer boundary contable. |
| Proceso muere a mitad de ventana | Fila parcial queda con `is_incomplete=1`. Reiniciar discover la siguiente ventana. |

## Punto de retoma para mañana / OpenClaw

1. **Verificar estado del logger** (si sigue corriendo de esta sesión o necesita re-lanzar):
   ```powershell
   Get-Process python -ErrorAction SilentlyContinue
   Get-Content "D:\openclaw\PROJECT DESIGN\reports\live\continuous_stdout.log" -Tail 10
   ```

2. **Si está corriendo y todo va bien**, dejarlo correr hasta llegar a 1000 ventanas con `is_incomplete=0`. Monitor cada N horas.

3. **Si está detenido**, evaluar:
   - ¿Cuántas ventanas válidas hay en la DB ya?
   - Si suficientes (≥3 con outcome=Up/Down) → smoke L-6 PASS, arrancar la corrida real de 1000.
   - Si insuficientes → relanzar y observar.

4. **Notebook `notebooks/analysis.ipynb`** sigue pendiente (Fase 7). NO es bloqueante para Fase 6.

## Decisión clave registrada
- Logger persistente cumple PROJECT_DESIGN §9 literal.
- Modo `--continuous` es opt-in. Los modos `--one-window-pilot` y `--demo-once` siguen funcionando idénticos.
- User-Agent es estándar para todas las requests HTTP del proyecto.

Generado: 2026-05-28T03:07Z (aproximado, sesión activa).
