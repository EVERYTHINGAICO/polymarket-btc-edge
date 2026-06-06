# T4 Manual Network Cut Report Template

## Estado
- Resultado: PASS / FAIL / ABORTED
- Fecha UTC:
- Operador humano:
- Host / entorno:

## Precondiciones verificadas
- [ ] T1 = PASS
- [ ] T2 = PASS
- [ ] T3 = PASS
- [ ] Logger corriendo en modo supervisado
- [ ] Logs visibles durante la prueba
- [ ] Ruta de SQLite identificada
- [ ] Ventana activa identificada antes del corte

## Contexto de la ventana afectada
- `window_id`:
- `ts_open` (UTC):
- `ts_close` esperado (UTC):
- Hora UTC exacta del corte:
- Hora UTC exacta de restauración:
- Duración aproximada de la caída:

## Evidencia observada
- Señales de desconexión en logs:
- Señales de reconexión en logs:
- Ventana afectada marcada `is_incomplete`:
- Ventana afectada marcada `insufficient_flow`:
- Campo `notes` relevante:
- ¿Se evitó duplicación de filas?: sí / no
- ¿Se evitaron rellenos artificiales?: sí / no

## Criterios PASS/FAIL
### PASS
- El sistema reconecta tras restaurar red.
- La ventana afectada queda marcada como incompleta y/o de flujo insuficiente.
- No se inventan datos ni se rellenan huecos.
- No se duplican filas.
- La siguiente ventana vuelve a procesarse normalmente.

### FAIL
- No reconecta.
- La ventana queda falsamente completa.
- Se rellenan datos inexistentes.
- Se duplican o corrompen filas.
- El sistema queda en estado inconsistente tras la caída.

## Extractos mínimos de evidencia
- Línea(s) de log antes del corte:
- Línea(s) de log durante la caída:
- Línea(s) de log tras la reconexión:
- Resumen de la fila SQLite afectada:

## Veredicto final
- Resultado:
- Observaciones:
- Siguiente acción recomendada:
