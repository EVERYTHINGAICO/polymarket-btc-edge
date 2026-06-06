# Live Execution Runbook

## Estado

Proyecto auditado y listo para ejecución live supervisada.

No marcar PASS automático para:
- T1 integridad Deribit 1 hora
- T3 fidelidad temporal live
- T4 corte manual de red
- recolección oficial de ~1000 ventanas
- gates estadísticos con datos reales

## Reglas operativas

- No modificar `PROJECT_DESIGN.md`
- No usar secretos
- No usar trading ni órdenes reales
- No usar APIs en modo escritura
- Supervisión humana obligatoria durante pruebas live y arranque de recolección
- Registrar resultados reales, no estimados

## Preparación previa

1. Entrar al directorio del paquete:
   ```bash
   cd "/home/node/.openclaw/workspace/PROJECT DESIGN"
   ```
2. Activar entorno virtual si existe:
   ```bash
   source .venv/bin/activate
   ```
3. Instalar dependencias si hace falta:
   ```bash
   pip install -r requirements.txt
   ```
4. Ejecutar suite local antes de cualquier run live:
   ```bash
   python3 -m unittest tests.test_scaffold tests.test_db tests.test_deribit_feed tests.test_signal tests.test_polymarket_feed tests.test_logger
   python3 scripts/validate_system.py
   python3 scripts/stat_validate.py
   ```

## T1 — Integridad de captura Deribit (run humano)

### Objetivo
Verificar durante ~1 hora que la captura de trades Deribit es razonable y que no quedan trades sin clasificar por un bug obvio.

### Procedimiento
1. Ejecutar el feed read-only de Deribit en consola:
   ```bash
   python3 -m src.deribit_feed | tee reports/deribit_live_t1.log
   ```
2. Mantenerlo corriendo aproximadamente 1 hora.
3. Tomar nota de:
   - hora UTC de inicio
   - hora UTC de cierre
   - cantidad aproximada de trades impresos
   - cantidad de líneas `skipped_trade`
   - cualquier línea `retrying_deribit_feed`
4. Comparar de forma manual el orden de magnitud contra volumen/trades públicos visibles de Deribit para esa ventana.
5. Guardar un resumen humano en:
   `reports/phases/fase_5v_t1_human_result.md`

### Criterio
- PASS humano si el volumen capturado es razonable y los `skipped_trade` no muestran un patrón de parseo roto.
- FAIL humano si hay descarte alto sin explicación clara o desconexiones que rompen la observación.

## T3 — Fidelidad temporal live

### Objetivo
Verificar que timestamps UTC y snapshots de apertura/cierre se alinean con ventanas reales.

### Procedimiento
1. Seleccionar una o varias ventanas reales de 15 minutos.
2. Registrar manualmente:
   - hora UTC exacta de apertura esperada
   - `price_to_beat`
   - snapshot de ventana activa desde Polymarket
   - timestamp de apertura observado por el sistema
3. Confirmar que la apertura registrada esté alineada dentro de pocos segundos respecto a la ventana real.
4. Documentar resultado en:
   `reports/phases/fase_5v_t3_human_result.md`

### Criterio
- PASS humano si el alineamiento UTC es consistente.
- FAIL humano si aparecen desfases sistemáticos o timestamps ambiguos.

## T4 — Corte manual de red

### Objetivo
Verificar que una interrupción real no inventa completitud y deja la ventana marcada como incompleta o con hueco.

### Procedimiento
1. Iniciar una sesión de observación controlada.
2. A mitad de una ventana, cortar la red manualmente o bloquear temporalmente conectividad.
3. Restaurar red.
4. Verificar que el sistema:
   - no inventa datos faltantes
   - deja marcas de `is_incomplete` y/o `insufficient_flow`
   - conserva notas de runtime relevantes
5. Documentar resultado en:
   `reports/phases/fase_5v_t4_human_result.md`

### Criterio
- PASS humano si la ventana queda marcada de forma conservadora.
- FAIL humano si parece completa pese al corte o si el proceso queda en estado engañoso.

## Recolección oficial supervisada

### Objetivo
Acumular ~1000 ventanas completas y confiables.

### Procedimiento operativo
1. No arrancar hasta decidir el host estable y confirmar supervisión humana.
2. Crear respaldo del directorio `reports/` antes de runs largos.
3. Ejecutar el logger real únicamente en modo autorizado por el proyecto.
4. Monitorear periódicamente:
   - crecimiento de la base SQLite
   - cantidad de ventanas completas
   - cantidad de ventanas incompletas
   - señales de desconexión o bajo flujo
5. No dejar correr sin observabilidad básica.
6. Al llegar a muestra suficiente, congelar la base y correr:
   ```bash
   python3 scripts/stat_validate.py
   ```
7. Si ya hay >=1000 ventanas completas, preparar los gates estadísticos reales.

## Entregables humanos esperados

Crear estos archivos con veredicto real:
- `reports/phases/fase_5v_t1_human_result.md`
- `reports/phases/fase_5v_t3_human_result.md`
- `reports/phases/fase_5v_t4_human_result.md`
- `reports/phases/fase_6_collection_human_status.md`

## Estado final esperado antes de estadística real

- T1: ejecutado por humano
- T3: ejecutado por humano
- T4: ejecutado por humano
- base SQLite con muestra suficiente
- `scripts/stat_validate.py` deja de responder `INSUFFICIENT_DATA`
