# Changelog

## v1.6 (2026-10-21)
- `correr_pluribus.ps1`: nuevos parametros `-Recalibrar`, `-SoloValidar` y `-Datos <carpeta>`
  (reutiliza un dataset ya descargado). Sin cambios en el codigo del sistema.

## v1.5 (2026-10-21)
- Nuevo: `validacion_temporal(..., recalibrar=True)` y `scripts/validar_temporal.py --recalibrar`.
  Temperatura ajustada con el 20 % final del entrenamiento (cronologico), sin usar la prueba.
  Reporta T, logloss y ECE del mismo modelo antes y despues de recalibrar.
  Con 3000 manos simuladas el logloss mejora en 5 de 5 pliegues (poco: 0.001 a 0.007) y el ECE queda mixto.
- Pruebas: 126.

## v1.4 (2026-10-21)
- Rendimiento: `ModeloRangos.predecir` calculaba el posterior 169 veces por decision; ahora una sola vez.
  Resultados identicos (verificado con la validacion temporal sobre 3000 manos simuladas).
  Relevante con datasets grandes: la validacion sobre 10000 manos de Pluribus tardaba varios minutos.

## v1.3 (2026-10-21)
- Nuevo: `correr_pluribus.ps1` (Windows/PowerShell). Clona el dataset PHH, corre la validacion temporal
  con datos reales y la carga en modo `--simular`; con `-Cargar` sube a Supabase pidiendo
  `DATABASE_URL` y `POKER_SAL` sin mostrarlas ni guardarlas. Sin cambios en el codigo del sistema.

## v1.2 (2026-10-21)
- Nuevo: curva de calibración y ECE por pliegue en `validacion_temporal`; el script escribe
  `resultados/validacion_temporal_calibracion.csv` y muestra el ECE por pliegue.
- Sin cambios en el resto. Pendientes externos: archivo real de tu sitio para validar el parser
  y la carga a Supabase desde tu máquina.

## v1.1 (2026-10-21)
- Nuevo: c-bet % y fold to c-bet % en `estadisticas.py` (RF-03), con 6 pruebas de casos límite
  (`tests/test_cbet.py`): apuesta previa del rival, agresor que chequea, subida sobre la c-bet, sin flop.
- Nuevo: `validacion_temporal` en `rangos.py` y `scripts/validar_temporal.py` (plan, sección 7).
  Resultado con 3000 manos simuladas: el modelo supera al base en logloss en 5 de 5 pliegues
  (`resultados/validacion_temporal.csv`).
- Cambio: columnas `cbet` y `fold_cbet` en panel, ventana de escritorio y CSV
  (`panel.py`, `app/ventana.py`, `analizar_real.py`, `simular.py`).
- Pruebas: 125 (antes 117).
- Sin cambios: carga a Supabase, parsers, esquema.

## v1.0
- Base: motor, evaluador, equity, estadísticas, rangos, PHH y texto estilo PokerStars, panel, carga a Supabase.
