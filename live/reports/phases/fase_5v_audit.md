# Fase 5.V Audit

PASS_WITH_PENDING_HUMAN_RUNS

## fase ejecutada
Fase 5.V — validación del sistema T1–T5

## implementado
- Harness local: `scripts/validate_system.py`
- Cobertura local de T2 y T5 mediante unit tests existentes
- Plan explícito para T1, T3 y T4 sin falsificar ejecución live

## pruebas ejecutadas
- `python3 -m unittest tests.test_signal`
- `python3 -m unittest tests.test_db tests.test_logger`
- `python3 scripts/validate_system.py`

## pendientes de ejecución humana
- T1 integridad de captura Deribit durante ~1 hora
- T3 fidelidad temporal contra apertura real de ventana Polymarket
- T4 corte manual de red y verificación de ventana incompleta

## riesgos restantes
- Sin los runs live, la validación técnica completa no puede declararse cerrada al 100%

## si requiere aprobación humana
- Sí, para ejecutar T1/T3/T4 en condiciones reales
