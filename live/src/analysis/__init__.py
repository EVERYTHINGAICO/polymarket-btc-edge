"""Analisis estadistico determinista para PROJECT_DESIGN seccion 7.B.

Modulo puro: toda la logica de los 4 gates vive aqui. Notebook y CLI son
solo presentacion. Garantiza reproducibilidad bit-exact via:
- Pre-registro JSON versionado (analysis_config.json)
- Hash SHA256 del input + output
- Random seeds fijas
- Synthetic fixtures para validacion
- Bonferroni correction multiple-testing
- K-fold cross-validation

Read-only sobre data/observations.db.
"""
