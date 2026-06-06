# Fase 6 Readiness Report

PASS_WITH_HUMAN_START_GATE

## objetivo
Preparar la recolección oficial read-only sin lanzar aún una corrida prolongada.

## comando reproducible propuesto
```bash
python3 -m src.logger --db data/observations.db --log-path reports/live/logger_runtime.log
```

## observabilidad mínima
- logs UTC en `reports/live/logger_runtime.log`
- base SQLite en `data/observations.db`
- reportes de ciclo en `reports/cycles/`

## criterios de ventana confiable
- apertura/cierre UTC alineados
- sin inventar completitud
- `is_incomplete=0` y `insufficient_flow=0` para ventanas confiables
- sin duplicados ni corrupción tras stop/resume

## stop/resume
- detener proceso manualmente con supervisión humana
- reiniciar sobre la misma DB
- validar que no aparezcan duplicados

## límites
- no iniciar aún recolección prolongada desde este paso
- requiere gate humano antes del arranque supervisado
