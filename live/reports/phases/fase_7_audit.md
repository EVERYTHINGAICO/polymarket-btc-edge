# Fase 7 Audit

PASS_WITH_DATA_PENDING

## fase ejecutada
Fase 7 — validación estadística solo lectura

## implementado
- Script `scripts/stat_validate.py`
- El script lee SQLite solo en modo lectura lógica y reporta `INSUFFICIENT_DATA` si faltan ventanas completas

## criterio actual
- Requiere ~1000 ventanas completas antes de cualquier conclusión estadística
- No inventa resultados ni fuerza gates 1–4 sin muestra suficiente

## si requiere aprobación humana
- Sí, para aportar/recolectar la muestra real necesaria
