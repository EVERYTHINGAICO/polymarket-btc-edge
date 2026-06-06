# T4 Manual Network Cut Checklist

## Precondiciones
1. Confirmar estado actual:
   - T1 = PASS
   - T2 = PASS
   - T3 = PASS
   - T4 = PENDING_MANUAL_NETWORK_CUT
   - T5 = NOT_STARTED
2. Confirmar que el logger está listo para corrida supervisada.
3. Confirmar acceso a logs en tiempo real.
4. Confirmar que el archivo SQLite de observaciones es inspeccionable.
5. Confirmar que NO se va a modificar firewall/VPN/SO más allá del corte humano temporal de conectividad.

## Pasos humanos
1. Iniciar corrida supervisada del logger en un host estable.
2. Esperar una ventana activa y anotar:
   - `window_id`
   - `ts_open` UTC
   - `ts_close` esperado UTC
3. Dejar correr unos minutos para confirmar flujo normal.
4. A mitad de la ventana, cortar conectividad temporalmente.
5. Registrar hora UTC exacta del corte.
6. Esperar suficiente tiempo para introducir un hueco real de datos.
7. Restaurar conectividad.
8. Registrar hora UTC exacta de restauración.
9. Esperar reconexión del sistema.
10. Al cierre de la ventana afectada, revisar la fila SQLite y los logs.
11. Completar la plantilla `t4_manual_network_cut_template.md`.

## Timestamps UTC a registrar
- Inicio de la corrida
- `ts_open` de la ventana afectada
- Hora UTC del corte
- Hora UTC de restauración
- Hora UTC de reconexión observada
- `ts_close` de la ventana afectada

## Evidencia esperada
- Logs de desconexión
- Logs de reconexión
- Fila SQLite con `is_incomplete=1` y/o `insufficient_flow=1`
- `notes` con contexto útil si existe
- Confirmación de ausencia de duplicación o relleno artificial

## Criterio de cierre
- PASS si la caída queda reflejada de forma conservadora y el sistema continúa sano.
- FAIL si la ventana aparece falsamente completa, si no reconecta o si se corrompen/duplican datos.
