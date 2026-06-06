# Fase 6 Audit

PASS_WITH_PENDING_HUMAN_RUN

## fase ejecutada
Fase 6 — preparación de recolección oficial

## implementado
- Runbook conservador para ejecución manual/acotada
- Stub `scripts/run_collection_once.py` para recordar que no debe lanzarse recolección indefinida desde este runtime sin confirmación humana

## runbook resumido
1. Activar entorno virtual e instalar requirements.
2. Confirmar que T1/T3/T4 fueron ejecutados o aceptados como pendientes controlados.
3. Iniciar logger en un host estable con supervisión humana.
4. Monitorear crecimiento de SQLite hasta ~1000 ventanas completas.
5. No introducir credenciales ni modos de escritura externos.

## si requiere aprobación humana
- Sí, para iniciar cualquier recolección live prolongada
