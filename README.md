# Análisis estadístico de Texas Hold'em

Proyecto de análisis estadístico para Texas Hold'em No Limit. Estado actual: **motor de partida, bots, estadísticas, simulación, inferencia de rangos, panel en streaming y carga a base de datos completos** (la carga por COPY se verificó contra PostgreSQL 16 real). El importador PHH está validado con manos reales (Pluribus, WSOP, HandHQ). El importador de texto estilo PokerStars/GGPoker **aún no se validó con un archivo real**.

## Estructura

```
poker_analisis/   código del proyecto
  cartas.py       Carta, Mazo (Fisher-Yates, semilla opcional)
  evaluador.py    evaluar_cinco, evaluar_mejor (5 a 7 cartas, directo) y evaluar_mejor_referencia (lento, para pruebas)
  equity.py       equity Monte Carlo con error estándar, probabilidad exacta de mejora, outs
  equity_rangos.py equity contra un rango o contra el posterior del modelo de rangos
  phh.py          importador del formato PHH (TOML), con rechazos explicados y orden natural de archivos
  real.py         manos PHH reales -> ResultadoMano (montos inferidos, netos, stacks)
  ggpoker.py      importador de historiales de texto estilo PokerStars/GGPoker (sin validar con archivo real)
  motor.py        partida completa: blinds, apuestas, all-in, botes laterales, conservación de fichas
  bots.py         perfiles de referencia: tight-agresivo, pasivo, aleatorio
  simulacion.py   mesa simulada de 6 bots con stacks acotados
  estadisticas_completas.py  estadísticas por posición y calle, con muestra e intervalo de Wilson (ver CHANGELOG v2.3)
  estadisticas.py VPIP, PFR, 3-bet, AF, WTSD, W$SD, c-bet, fold to c-bet, bb/100 con intervalo de confianza
  rangos.py       modelo bayesiano de rangos preflop, calibración y validación temporal
  riesgo.py       drawdown, probabilidad de ruina, Kelly
  panel.py        lógica del panel de escritorio (sin interfaz, con pruebas); procesa las manos en una sola pasada
  almacen.py      manos -> filas para la base, con jugadores seudonimizados
  carga.py        sentencias SQL idempotentes; carga por lotes con executemany o con COPY (`cargar_copy`)
app/              ventana.py: aplicación de escritorio (Tkinter); web.py y static/: panel web local de estudio
  texturas.py     (en poker_analisis/) textura del tablero y tamaño de apuesta sugerido
  practica.py     (en poker_analisis/) modo práctica: manos contra bots con la guía en vivo
  guia.py         (en poker_analisis/) repaso acción por acción y línea sugerida
db/               schema.sql: esquema para Supabase
scripts/          tabla_preflop, simular, evaluar_rangos, evaluar_contexto, validar_temporal, analizar_real,
                  analizar_handhq, equity_rango, cargar_supabase, validar_importacion
resultados/       salidas generadas por los scripts
tests/            pruebas unitarias, referencias conocidas y verificación exhaustiva
docs/             alcance, decisiones, resultados y documento técnico final
```

## Instalación e inicio

Solo hace falta Python 3.11 o más nuevo; no hay nada más que instalar (el proyecto usa la biblioteca estándar).
Descomprimí la carpeta y, desde ella:

```
iniciar.bat --demo          # Windows (doble clic también sirve; sin --demo abre el panel vacío)
./iniciar.sh --demo         # macOS o Linux
python iniciar.py --demo    # en cualquier sistema
```

Todo corre en tu computadora: las manos y los videos no salen de ella.

## Panel web de estudio

```
python3 app/web.py --demo                         # manos simuladas por los bots
python3 app/web.py --carpeta RUTA --formato phh   # tus historiales (phh o texto)
```

Se abre en http://127.0.0.1:8799. Pestañas: Panel (filtros, curva, posiciones, jugadores), Bloques de 1000, Práctica (jugás contra bots con la guía en vivo), Repaso con video
(mesa, cinta de equity, guía y video sincronizado por marcas) y Situación (análisis de una mano escrita a mano).
Atajos en el repaso: flechas izquierda y derecha cambian de paso, arriba y abajo de mano, M marca el paso en el video,
barra espaciadora reproduce. Es una herramienta para repasar manos ya jugadas, no para usar en vivo.

## Validar tus historiales de texto (Fase 0)

```
python3 scripts/validar_importacion.py RUTA_A_TUS_HISTORIALES --muestra 30
```

Escribe en `resultados/`: `validacion_rechazos.csv` (mano, archivo y motivo de cada rechazo), `validacion_resumen.txt`
(totales, motivos, archivos con más rechazos, controles de integridad) y `validacion_muestra.md` (manos al azar con el
texto original y lo que entendió el importador, para revisar a mano). El importador exige que el bote reconstruido
coincida con el "Total pot" del resumen del historial.

## Ejecutar los tests

Desde la carpeta raíz del proyecto:

```
python3 -m unittest discover -s tests -t .      # toda la suite, incluida la verificación de las 2.598.960 manos de cinco cartas
```

`tests/test_motor.py` incluye una prueba de estrés de 2.000 manos con apuestas, all-in y empates al azar, que verifica la conservación de fichas en cada una.

Documento técnico final: `docs/04_documento_tecnico_final.md`.

## Alcance

Solo Texas Hold'em. Omaha queda fuera de la demo (ver `docs/01_alcance_etapa0.md`).

## Tabla preflop

```
python3 scripts/tabla_preflop.py 4000   # ~10 s (v1.9; antes ~2,5 min); error estándar ≈ 0,7 pts por mano
```

## Simulación de mesa

```
python3 scripts/simular.py 3000 7    # 3.000 manos, semilla 7; ~8 s (v1.9; antes ~2,5 min)
```

Mesa de 6 jugadores con stacks de 100 BB, blinds 1/2. El stack máximo es de 100 BB: lo que excede se retira y quien queda por debajo de 2 BB recarga. Los resultados quedan en `resultados/estadisticas_simulacion.csv`.

**Cómo leer los resultados.** Con 3.000 manos, el intervalo de confianza de bb/100 ronda los ±200 a ±280. Una diferencia menor que eso entre dos perfiles no es concluyente. Para comparar estilos con un margen estrecho hacen falta del orden de 100.000 manos. La suma de bb/100 de todos los perfiles es cero, porque cada mano es de suma cero.

## Inferencia de rangos preflop

```
python3 scripts/evaluar_rangos.py 4000 11   # simula, entrena (75 %) y prueba (25 %); la simulación es ~15 veces más rápida desde v1.9
```

El modelo (`poker_analisis/rangos.py`) mantiene una distribución sobre las 169 manos, con prior ponderado por combinaciones. Cada acción preflop del jugador actualiza esa distribución según la probabilidad aprendida de la acción para cada mano y perfil. Como la simulación conoce las cartas de todos, la predicción se contrasta con lo que realmente pasó.

Resultados con 4.000 manos (semilla 11), sobre 1.000 manos de prueba:

| Perfil | Logloss modelo | Logloss base | Mejora | Acierto top-1 |
|---|---|---|---|---|
| TAG-1 | 0,823 | 0,910 | 9,6 % | 66 % |
| TAG-2 | 0,837 | 0,931 | 10,1 % | 66 % |
| TAG-3 | 0,812 | 0,897 | 9,5 % | 67 % |

_Estas cifras se midieron con los bots TAG anteriores a la recalibración (umbral preflop 0,55; juegan cerca del 37 % de las manos). Para reproducirlas, simular con `umbral_tag=0.55`; con el umbral actual (0,60) no se recalcularon._
| Pasivo-1 | 0,136 | 0,140 | 2,7 % | 97 % |
| Pasivo-2 | 0,159 | 0,163 | 2,7 % | 96 % |
| Aleatorio | 1,125 | 1,123 | −0,2 % | 46 % |

Lectura:
- El modelo aprende los perfiles con estilo consistente (TAG), que tienen un umbral claro por mano.
- No inventa información donde no la hay: en el aleatorio, la mejora es nula.
- Los pasivos casi no se pueden mejorar: su comportamiento base ya es casi determinista.
- **Calibración**: ECE de 0,038 sin ajustar. El error no es uniforme: en 0,5–0,6 el modelo es subconfiado (confianza 0,54, acierto real 0,66), y en 0,6–0,7 es sobreconfiado (0,63 contra 0,61). Por eso un escalado de temperatura único no lo corrige (T = 1,05, ECE 0,039).
- Una calibración isotónica pura bajaba el ECE a 0,021, pero destruía al aleatorio: asignaba confianza casi cero a un tramo con pocos datos, y el logloss subía a 3,6. Se corrigió mezclándola con la predicción original (λ = 0,25, elegido en validación). El resultado final es ECE 0,037 con el aleatorio estable (−1,5 %).

**Corrida de 20.000 manos** (`python3 scripts/evaluar_rangos.py 20000 11`, ~25 min antes de v1.9, 12.000 entrenamiento / 3.000 validación / 5.000 prueba):

- ECE sin calibrar: 0,015. Con escalado de temperatura (T = 1,05): **0,012**. La isotónica mezclada eligió λ = 0 en validación, así que no aporta con esta muestra y no se usa.
- Con más datos, el error de calibración se reduce a la mitad respecto de las 4.000 manos. La versión recomendada es la de temperatura.
- Logloss en prueba: TAG 0,76 a 0,79, pasivos 0,14 a 0,15, aleatorio 1,12.

**Posición y rivales** (`python3 scripts/evaluar_contexto.py 4000 11`):

| Variante | Logloss TAG-1 | Logloss Pasivo-1 | ECE |
|---|---|---|---|
| Base (sin contexto) | 0,822 | 0,123 | 0,014 |
| Con posición | 0,786 | 0,093 | 0,011 |
| Posición + rivales que entraron | 0,766 | 0,096 | 0,017 |

Comparar la columna "mejora %" entre variantes no es válido, porque cada una se mide contra su propio base. Lo correcto es comparar el logloss absoluto.

- Agregar posición mejora la predicción de forma consistente en todos los perfiles.
- Agregar rivales que entraron mejora más a los TAG, pero empeora la calibración (ECE 0,017): el contexto más fino tiene menos datos por celda.
- **Advertencia.** Los bots TAG ajustan su rango según la posición, así que parte de la mejora está construida en la simulación. Con humanos, el efecto de la posición tiene que medirse sobre el dataset real.

**Advertencia.** Los bots tienen umbrales fijos, así que esto es un caso favorable. Con jugadores humanos, que son ruidosos y cambian de estrategia, la mejora será menor. El modelo base no usa posición ni las acciones de los otros jugadores (son opcionales: `con_posicion` y `con_rivales`, ver más abajo), y ninguna variante usa historia entre manos.

## Manos reales (dataset PHH)

Fuente: dataset PHH público, repositorio [uoftcprg/phh-dataset](https://github.com/uoftcprg/phh-dataset). Datos publicados por Juho Kim (Universidad de Toronto) con licencia **CC BY 4.0** (Zenodo 13997158). El código del repositorio es MIT. Atribuir la fuente en cualquier publicación.

El dataset completo pesa 17 GB; el proyecto no lo incluye. Para correr el análisis, clonarlo en una carpeta y pasar la ruta:

```
python3 scripts/analizar_real.py /ruta/al/phh-dataset/data/pluribus
```

**Validación del importador** (`poker_analisis/real.py`):
- Pluribus: 10.000 manos válidas, 0 rechazos. En las 10.000 la suma de netos es cero. Es la prueba de que las apuestas inferidas y los stacks cuadran.
- WSOP: 11 manos No Limit válidas. Las 72 restantes son Omaha, stud y mixtos, y se rechazan con su motivo. El control de alcance funciona.
- HandHQ (2009, online, 1 $ a 1.000 $ de blind grande): soportado para estadística de acciones y resultados. Sus cartas están casi todas ocultas, así que no sirve para evaluar el modelo de rangos (ver sección HandHQ).

**Resultados sobre manos reales** (Pluribus, 10.000 manos, 7.500 entrenamiento / 2.500 prueba):

| Jugador | Manos | VPIP | PFR | bb/100 | ±IC95 |
|---|---|---|---|---|---|
| MrBlue | 9.121 | 31,4 % | 18,8 % | +16,5 | ±18 |
| Eddie | 5.510 | 27,2 % | 17,6 % | +12,2 | ±25 |
| Budd | 2.509 | 25,1 % | 18,1 % | +28,7 | ±36 |
| MrOrange | 7.512 | 20,8 % | 14,3 % | −12,1 | ±18 |
| Gogo | 488 | 31,8 % | 22,7 % | −57,2 | ±99 |

Lectura: con este número de manos ningún jugador es distinguible de cero. Los intervalos cubren desde ganancias grandes hasta pérdidas grandes.

**Modelo de rangos sobre humanos.** La mejora sobre el base es de 0,1 a 0,9 %, muy lejos del 10 % que se veía con bots. El ECE sin calibrar es 0,008, razonable. **Conclusión: la ventaja medida en simulación no se transfiere a jugadores humanos.** Los humanos son menos deterministas que los bots con umbral fijo, y el base por perfil ya captura la mayor parte de lo predecible con este contexto.

## Muestra de HandHQ (online, 2009)

Fuente: dataset PHH público (Juho Kim, Universidad de Toronto), CC BY 4.0. Los jugadores están seudonimizados.

```
python3 scripts/analizar_handhq.py /ruta/al/phh-dataset/data/handhq 25
```

Muestra: 25 archivos por nivel de No Limit (semilla 1), 25 a 1.000 NL. Resultados en `resultados/estadisticas_handhq_muestra.csv`.

| Nivel | Manos válidas | Rechazadas | VPIP | PFR | 3-bet | AF | WTSD | Mediana neto/mano (bb) |
|---|---|---|---|---|---|---|---|---|
| 1.000 NL | 23.777 | 994 | 26,4 % | 17,6 % | 6,9 % | 2,61 | 14,3 % | −3,10 |
| 600 NL | 23.318 | 1.379 | 26,8 % | 16,9 % | 6,5 % | 2,60 | 13,9 % | −2,00 |
| 400 NL | 23.982 | 888 | 26,1 % | 16,0 % | 6,1 % | 2,54 | 15,6 % | −3,50 |
| 200 NL | 22.325 | 2.285 | 26,0 % | 15,7 % | 5,8 % | 3,09 | 8,8 % | −4,50 |
| 100 NL | 23.863 | 562 | 24,8 % | 14,1 % | 5,5 % | 2,48 | 16,5 % | −5,00 |
| 50 NL | 20.659 | 4.246 | 26,4 % | 13,1 % | 4,2 % | 3,82 | 2,7 %* | −3,50 |
| 25 NL | 20.593 | 4.321 | 22,1 % | 10,1 % | 3,0 % | 3,32 | 5,0 %* | −3,00 |

\* En 50 y 25 NL el dataset no trae cartas conocidas, así que el WTSD se basa en showdowns que no se pueden verificar y no es comparable con los otros niveles.

**Cómo se calcula el neto.** HandHQ registra `winnings` como lo que cada jugador cobró del bote, no su ganancia neta. El neto es `winnings` menos las fichas que puso (ciegas, llamadas y subidas). Así la suma de netos de cada mano queda negativa: es el rake, que el dataset no registra por separado. Los netos se expresan en big blinds de cada mano.

**Por qué se usa la mediana.** La media de netos por mano está arrastrada por unas 20 manos de cada 20.000 con pérdidas mayores de 200 bb. Son manos válidas dentro de stacks finitos, pero distorsionan el promedio. La mediana (−2 a −5 bb por mano) es el rake esperado.

**Rechazos.** Cada rechazo tiene un motivo:
- *Sin `winnings` ni `finishing_stacks` (≈ 15–20 % de las manos):* el registro no trae resultado, así que no se puede calcular el neto.
- *Winnings mayores que lo invertido en el bote:* el registro reparte más fichas de las que existieron. Son 254 manos en 1.000 NL, y 231 de ellas son botes sin ninguna subida (todos limpian o se retiran). El filtro deja fuera un tipo concreto de bote, así que las estadísticas de esta muestra subrepresentan esos botes.
- *Menos de dos ciegas:* casos marginales, pocos en la muestra.

Por eso la muestra es descriptiva. Los rechazos no son aleatorios respecto del tipo de bote, y no se usan para evaluar el modelo de rangos.

## C-bet y validación temporal
- **C-bet %**: apuesta en el flop del último agresor preflop, sobre las veces que le toca actuar sin apuesta previa.
- **Fold to c-bet %**: retiros ante una c-bet, sobre las veces que se la enfrenta antes de que alguien suba.
  Una oportunidad por jugador y mano. Disponibles en el panel, la ventana y los CSV.
- **Validación temporal** (`validacion_temporal` en `rangos.py`): origen móvil, se entrena con el pasado y se evalúa
  en el bloque siguiente, sin fuga del futuro. Reporta logloss y Brier frente al modelo base por pliegue.
  Cada pliegue incluye ECE y su curva de calibración (`validacion_temporal_calibracion.csv`).
  Con `--recalibrar` agrega la temperatura ajustada solo con el pasado (sin usar la prueba).
  Script: `python3 scripts/validar_temporal.py [ruta_phh] [pliegues]` (sin ruta, simula bots).
  Las manos deben llegar en orden cronológico.

## Equity contra rangos (RF-06)
`equity_contra_rango(mano, rango, tablero)` estima la equity contra una distribucion sobre manos canonicas
(Monte Carlo, con IC95). `equity_contra_modelo` usa el posterior del modelo de rangos dado el historial preflop
de un jugador. Linea de comandos: `python3 scripts/equity_rango.py --mano "Kh Kd" --rango "AA,KK:0.5,AKs"`.
El rango es preflop: no se actualiza con las acciones postflop.

## Orden de carga

`cargar_directorio` (PHH y texto) recorre carpetas y archivos en **orden natural**: `2.phh` va antes que
`10.phh`. La validación temporal necesita las manos en orden cronológico: si el PHH trae `year`, `month`, `day` y
`time`, la fecha de la mano queda en `ResultadoMano.fecha` (hora sin zona = UTC) y se guarda en `jugada_en`.
Sin fecha, ese orden de archivos es lo único que la respalda. El drawdown del panel también usa la fecha cuando
todas las manos de un stake la tienen.

## Limitaciones actuales

- **W$SD no tiene la misma definición en todas las fuentes.** En la simulación y en los historiales de texto gana el showdown quien cobró algún bote; en PHH, quien termina con neto positivo (el formato no registra los cobros). Con rake o botes laterales no son directamente comparables.

- El parser PHH se validó con manos reales de Pluribus, WSOP y HandHQ (ver secciones "Manos reales" y "Muestra de HandHQ").
- Los bots son perfiles de referencia y no representan a jugadores humanos. Su postflop usa equity Monte Carlo con pocas iteraciones (60), por velocidad.
- La simulación no incluye rake, torneos ni comportamiento de tilt.

## Aplicación de escritorio

`python3 app/ventana.py` abre una ventana (Tkinter; en Linux requiere `python3-tk`) para elegir una
carpeta de manos `.phh`, ver estadísticas y riesgo por jugador y exportar a CSV. La lógica está en
`poker_analisis/panel.py` (con pruebas); la ventana no tiene pruebas automáticas. Desde v2.0 el análisis corre en un hilo aparte, así la ventana no se congela con carpetas grandes. El mínimo de manos
por perfil es un campo editable porque el umbral aún no está decidido.

## Base de datos y riesgo

`db/schema.sql` define el esquema para Supabase (aplicado con 10.000 manos de Pluribus, ver `docs/04_documento_tecnico_final.md`). Desde v2.0 la carga guarda `jugada_en`, pero las manos ya cargadas quedan con `jugada_en` nulo (la carga es `on conflict do nothing`). Para completarlo: `python3 scripts/completar_jugada_en.py --ruta <carpeta phh> --fuente <nombre>`. `poker_analisis/almacen.py` convierte
manos a filas con jugadores seudonimizados. `poker_analisis/riesgo.py` calcula drawdown, probabilidad de
ruina y bankroll de Kelly bajo el supuesto de manos independientes.

## Historiales de texto (estilo PokerStars)

`poker_analisis/ggpoker.py` importa historiales de texto con la estructura de PokerStars, que comparten
GGPoker y otros sitios (solo NLHE cash; monedas $, € y £). Se escribió según la estructura conocida y
**no se validó con un archivo real de ningún sitio**. Los montos se convierten a centavos. En la
aplicación, el big blind en "auto" separa las manos por stake.

## Carga a Supabase

`scripts/cargar_supabase.py` sube las manos (GGPoker o PHH) al schema `poker`. Se conecta con
`DATABASE_URL` y usa `POKER_SAL` (secreta y siempre la misma) para seudonimizar los jugadores. Requiere
`pip install "psycopg[binary]"`. Con `--simular` solo analiza y cuenta. La carga es idempotente.
Por defecto el script usa `cargar_copy` (COPY a tablas temporales e inserción por conjuntos, ~3 veces más rápido que
`cargar`). `tests/test_carga_postgres.py` compara ambos caminos contra una base PostgreSQL real y se omite salvo que
se defina `POKER_DSN_PRUEBA`. **Ojo:** esa prueba borra el schema `poker` de la base que se indique; usar una base de prueba.

## Atajo en Windows
`.\correr_pluribus.ps1` clona el dataset de Pluribus, valida con datos reales y simula la carga. Con `-Cargar` sube a Supabase.
