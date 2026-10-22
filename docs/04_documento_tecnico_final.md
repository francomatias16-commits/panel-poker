# Documento técnico final

Sistema de análisis estadístico de Texas Hold'em No Limit (cash). Versión 1.8, 2026-10-21.
Este documento cierra la Etapa 8 del plan: resume qué se construyó, con qué evidencia, qué no se logró
y qué falta para usarlo de forma sostenida. Las cifras salen de scripts del proyecto y se pueden reproducir (sección 9).

## 1. Alcance y restricción operativa

El sistema analiza historiales de mano ya jugados y simula partidas en un entorno propio. **No se conecta a salas
de terceros, no opera en tiempo real sobre mesas reales y no asiste decisiones en partidas con dinero real.** La
herramienta de equity contra rangos (`scripts/equity_rango.py`) es de análisis posterior o hipotético y no debe
usarse durante una partida: la mayoría de las salas lo prohíbe y puede implicar el cierre de la cuenta.

Omaha quedó fuera (decisión del 2026-10-20, ver `docs/02_decisiones.md`). El evaluador está diseñado para poder incorporarla.

## 2. Estado frente a los requisitos del plan

| Requisito | Estado | Evidencia |
|---|---|---|
| RF-01 importar historiales con validación | Cumplido con una salvedad | PHH validado con Pluribus (10.000 manos, 0 rechazos), WSOP y HandHQ. El importador de texto estilo PokerStars/GGPoker **no está validado con un archivo real de ningún sitio**. |
| RF-02 base relacional normalizada | Cumplido | Esquema `poker` en Supabase (5 tablas, RLS, solo rol de servicio). 10.000 manos de Pluribus cargadas desde la máquina del titular. No se cargan fecha de la mano ni torneos. |
| RF-03 estadísticas con intervalos de confianza | Cumplido | VPIP, PFR, 3-bet, c-bet, fold to c-bet, AF, WTSD, W$SD y bb/100 con IC95. |
| RF-04 rangos bayesianos por posición y acción | Cumplido, solo preflop | `rangos.py`: posterior sobre las 169 manos canónicas. |
| RF-05 probabilidades de acción calibradas | Cumplido, solo preflop | Sección 4. |
| RF-06 equity contra rangos estimados | Cumplido, solo preflop | `equity_rangos.py`. KK contra AA ≈ 18 %, AA contra KK ≈ 82 %. |
| RF-07 simulación con bots configurables | Cumplido | Motor con botes laterales y conservación de fichas; 6 perfiles de bots. |
| RF-08 reportes de rentabilidad y riesgo | Cumplido | bb/100, desvío, drawdown, probabilidad de ruina y Kelly (`riesgo.py`). |
| RF-09 dashboard | Cumplido | Aplicación de escritorio (Tkinter) y exportación CSV. Sin pruebas automáticas de la ventana. |
| RNF-01 reproducibilidad | Cumplido | Misma semilla, mismo resultado; con pruebas. |
| RNF-02 latencia < 100 ms por decisión | Cumplido | Medida el 2026-10-21 sobre 2.790 decisiones: mediana 0,05 ms, p99 0,10 ms, máximo 1,6 ms (modelo con posición, caché de matrices en caliente). |
| RNF-03 cobertura > 85 % en motor y evaluador | Cumplido | motor 90 %, evaluador 100 %, cartas 98 %, equity 93 %. Total del paquete 88 % con 138 pruebas. `bots.py` 52 % y `simulacion.py` 0 % (se usan desde scripts). |
| RNF-04 trazabilidad | Cumplido | Cada mano guarda referencia, ciega chica y archivo de origen. |
| RNF-05 documentación de supuestos | Cumplido | README, `docs/` y docstrings por módulo. |

## 3. Resultados con datos reales

**Pluribus, 10.000 manos (6 jugadores, ciegas 50/100).** Las 10.000 manos cuadran (suma de netos cero) y no hay rechazos.
Con este volumen ningún jugador se distingue de cero en bb/100 (intervalos de ±18 a ±99). Detalle en `docs/03_resultados_presentacion.md`.

**Validación temporal del modelo de rangos** (origen móvil, 5 pliegues, entrena solo con el pasado):

| Pliegue | Manos de entrenamiento | Logloss modelo | Logloss base | Brier modelo | Brier base | ECE |
|---|---|---|---|---|---|---|
| 1 | 1.666 | 0,869 | 0,870 | 0,495 | 0,495 | 0,140 |
| 2 | 3.332 | 0,784 | 0,786 | 0,459 | 0,459 | 0,072 |
| 3 | 4.998 | 0,677 | 0,679 | 0,403 | 0,404 | 0,014 |
| 4 | 6.664 | 0,680 | 0,682 | 0,404 | 0,405 | 0,014 |
| 5 | 8.330 | 0,685 | 0,688 | 0,409 | 0,410 | 0,019 |

El modelo supera al base en logloss en los 5 pliegues, pero por 0,001 a 0,003, es decir, entre 0,1 % y 0,4 %.
La recalibración por temperatura (ajustada con el 20 % final del entrenamiento, sin usar la prueba) no cambia el panorama:
T queda entre 1,00 y 1,10, el ECE del pliegue 1 pasa de 0,141 a 0,139 y en el pliegue 3 empeora de 0,012 a 0,027.
Por eso no se aplica por defecto.

## 4. Calibración: qué se logró y qué no

- Con **simulación** (20.000 manos), ECE 0,012 a 0,015 y mejora de logloss cercana a 14 % en perfiles con estilo consistente.
- Con **datos reales**, el ECE queda en 0,014 a 0,019 desde el tercer pliegue (más de 5.000 manos de entrenamiento), lo que cumple el criterio de éxito del plan.
  Con menos manos es mucho peor (0,140 y 0,072). Hipótesis, no verificada: con pocas manos las celdas por mano y contexto tienen pocos datos y los primeros bloques se parecen poco a los siguientes. Requiere más datos o un análisis por perfil para confirmarla.
- **La ventaja de la simulación no se transfiere a humanos ni a bots reales.** Es el hallazgo central: la mejora sobre el base pasa de ~10 a 14 % en la simulación a 0,1 a 0,4 % en Pluribus. Una predicción de acciones preflop por perfil no aporta mucho más que la frecuencia del propio perfil.

## 5. Limitaciones conocidas

1. Los rangos son solo preflop: no se actualizan con acciones postflop ni con el historial entre manos.
2. Equity contra un rango, no contra una distribución que dependa del tablero.
3. Los bots son perfiles de referencia; su postflop usa equity con 60 iteraciones, por velocidad.
4. No se modelan rake, torneos, tilt ni cambios de comportamiento en el tiempo.
5. El parser de texto no está validado con un archivo real. Un formato de otro sitio (888, iPoker) requiere un parser nuevo.
6. La carga no guarda fecha de la mano (`jugada_en`) ni datos de torneos. Sin fecha, la validación temporal depende del orden de los archivos.
7. Con 10.000 manos las métricas de rentabilidad tienen intervalos muy anchos; distinguir estilos requiere del orden de 100.000.
8. Datos históricos (HandHQ, 2009) no registran cartas ni rake y se rechaza entre 4 % y 20 % de sus manos.
9. La ventana de escritorio no tiene pruebas automáticas.

## 6. Riesgos del plan: estado

| Riesgo | Estado |
|---|---|
| Formatos de exportación cambian | Abierto: falta archivo real del sitio del titular. |
| Muestra insuficiente por jugador | Mitigado con IC95 y umbral configurable; sigue limitando las conclusiones. |
| Sobreajuste a un rival o período | Mitigado con validación temporal; se confirmó que el modelo no se sobreajusta, pero tampoco gana mucho. |
| Probabilidades mal calibradas | Mitigado desde ~5.000 manos de entrenamiento; abierto por debajo de eso. |
| Interpretación excesiva de resultados | Mitigado en la documentación; depende de cómo se presenten los reportes. |
| Términos de servicio | Abierto: revisar los de cada sitio antes de analizar historiales propios. |
| Privacidad de terceros | Mitigado: seudónimos con sal secreta; la base solo admite el rol de servicio. |
| Errores en el evaluador | Mitigado: verificado contra las 2.598.960 manos de cinco cartas. |

## 7. Seguridad y datos

- Las credenciales van en variables de entorno, nunca en código. El script de carga las pide sin mostrarlas y las borra al terminar.
- `POKER_SAL` debe ser siempre la misma; si se pierde no se pueden vincular los seudónimos. Está a cargo del titular.
- Incidente documentado: la cadena de conexión de la base de prueba se compartió en un chat durante la carga. La base solo tenía datos públicos de Pluribus; la clave debe rotarse (Settings → Database → Reset database password).
- Dataset PHH: CC BY 4.0, Juho Kim (Universidad de Toronto), Zenodo 13997158. TexasSolver (AGPL v3) no es dependencia del código.

## 8. Hoja de ruta a producción

Orden sugerido, de mayor a menor valor:

1. **Validar el parser con un archivo real** del sitio que use el titular (con datos personales removidos) y revisar sus términos de servicio. Hasta entonces, el análisis de historiales propios no está respaldado.
2. **Guardar la fecha de cada mano** (`jugada_en`) para que la validación temporal use tiempo real y no el orden de archivos.
3. **Más datos por jugador** (objetivo: 100.000 manos) o agrupar por tipo de jugador antes de reportar perfiles.
4. **Rangos postflop**: actualizar el posterior con acciones en flop, turn y river, y medir si aporta sobre el modelo preflop.
5. **Rake y torneos** en el esquema y en las métricas de rentabilidad.
6. **Pruebas de la ventana de escritorio** y empaquetado de un ejecutable para Windows.
7. **Omaha**, si hay un dataset verificado.
8. Rotación periódica de credenciales y revisión de políticas RLS al agregar usuarios.

## 9. Cómo reproducir

```
python3 -m unittest discover -s tests -t .
python3 scripts/simular.py 3000 7
python3 scripts/evaluar_rangos.py 20000 11
python3 scripts/validar_temporal.py <ruta>/data/pluribus 5 --recalibrar
python3 scripts/analizar_real.py <ruta>/data/pluribus
python3 scripts/equity_rango.py --mano "Kh Kd" --rango "AA,KK:0.5,AKs"
```

En Windows: `.\correr_pluribus.ps1 -Recalibrar -SoloValidar -Datos <carpeta del dataset>`.
