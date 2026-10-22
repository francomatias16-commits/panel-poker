# Changelog

## Fase 7 (parcial): pruebas de regresión de la guía
- `tests/test_guia_reglas.py`: 29 pruebas, una por regla de `guia.decidir` con situaciones armadas a mano: apertura por posición y tamaño (2,5 bb + 1 por limper), pot odds y EV de igualar, umbral de valor y su baja con más rivales, subir con monstruos, retirarse con aire, límites por stack, outs, rangos, familias de acciones y entradas inválidas.
- Control de calidad de las propias pruebas: se cambiaron a propósito 7 reglas de la guía (rango de UTG, tamaño de apertura, umbral de subida, fórmula de pot odds, umbral de valor, límite por stack, familia de la apuesta) y las 7 hacen fallar la suite. Una de ellas se había escapado porque la prueba usaba la misma función que verificaba; se corrigió con valores escritos a mano.
- 29 pruebas nuevas (373 en total).

## Fase 6 (parcial): alinear el video con las horas del historial
- `POST /api/alinear` y, en el panel de video, "Alinear por hora" (escribís la hora de inicio del video tal como figura en el historial) y "Alinear por esta marca" (marcás a mano una mano y el resto se ubica por su hora). Crea una marca por mano en su primer paso, respeta tus marcas manuales y deja fuera las manos anteriores o posteriores al video.
- Hora sin zona se lee igual que las del historial (la hora de reloj de la sala), así que no hay que convertir zonas.
- 6 pruebas nuevas (344 en total). Los pasos dentro de cada mano siguen marcándose a mano: el historial no trae la hora de cada acción.
- Pendiente: leer cartas y bote del video con visión por computadora (opcional, frágil, queda para el final).

## Fase 7 (parcial): inicio sencillo
- `iniciar.py`, `iniciar.bat` e `iniciar.sh`: arrancan el panel desde cualquier carpeta, verifican Python 3.11 o más nuevo con un mensaje claro y no requieren instalar nada (solo biblioteca estándar). Sección "Instalación e inicio" en el README. 3 pruebas nuevas.
- Velocidad medida, sin cambios necesarios: el repaso de una mano tarda ~0,3 s (y queda en caché); el informe de riesgo ya usa la simulación una sola vez (antes 15 s).
- Pendiente de la Fase 7: pruebas de regresión por cada regla de la guía y un instalador con ícono si lo querés.

## Fase 3 (parcial): EV de igualar con calles por delante
- `guia.realizacion`: factor de realización de equity (1 menos una pérdida por cada calle restante, mayor fuera de posición y con más rivales). La guía devuelve `realizacion` y `ev_igualar_realizado` junto al EV de siempre, y el panel los muestra cuando el factor es menor que 1. En el river vale 1.
- 2 pruebas nuevas (335 en total). Es informativo: no cambia la acción sugerida.
- Los factores son convenciones de estudio, no medidas (constantes al inicio de `guia.py`). No es un EV con simulación de las calles siguientes; eso y la comparación con un solver siguen pendientes.

## Fase 3 (parcial): texturas de tablero y tamaño de apuesta
- `poker_analisis/texturas.py`: clasifica el tablero (seca, media, mojada) por palos, conexión (el as cuenta alto y bajo) y pares, y sugiere la fracción del bote a apostar por valor: 33 % seco, 50 % medio, 75 % mojado (+10 puntos en turn y river si es mojado).
- La guía ya no apuesta siempre 2/3 del bote postflop: usa ese tamaño y lo explica en las razones.
- 5 pruebas nuevas (333 en total), con tableros construidos a mano.
- Los tamaños son convenciones de estudio, no resultados de un solver (constantes al inicio del módulo). Sigue pendiente de la Fase 3: rangos preflop más finos, EV a varias calles y la comparación contra salidas de un solver que aporte el usuario.

## Modo práctica contra bots
- `poker_analisis/practica.py`: jugás en el asiento 0 de una mesa de 6 contra bots (2 TAG, 2 pasivos y 1 aleatorio), con stacks que persisten entre manos y botón que rota. Cada mano se reconstruye desde cero con la misma semilla y tus acciones (los bots son deterministas), así que no hay estado de partida a medias.
- La guía responde en cada decisión con `guia.reproducir` sobre la mano a medias (equity contra rangos estimados, pot odds, línea sugerida). Solo usa lo que ves: las cartas de los rivales no salen del servidor hasta el showdown (hay pruebas de eso y de que la sugerencia no cambia si se cambian cartas ajenas).
- Al terminar la mano: showdown, resultado en bb, decisiones que coinciden con la guía y cada desvío con su gravedad. Acumulado de la sesión (bb, bb/100 solo desde 30 manos, % de coincidencia).
- Panel web: pestaña "Práctica" y `POST /api/practica` (acciones: nueva, estado, actuar, siguiente, guia). La guía se puede apagar para decidir primero y revisar después.
- 14 pruebas nuevas (328 en total).
- Límites: es una guía heurística, no un solver; un desvío "leve" es discutible. Una sesión por servidor local. Es para estudiar, no para usar en una sala con dinero.

## Fase 4: riesgo y bankroll con incertidumbre
- `poker_analisis/bankroll.py` (no toca `riesgo.py`): en cada escenario se sortean un winrate y un desvío plausibles dados los datos, así que cada cifra es predictiva y trae junto lo que daría tomar el winrate observado como verdadero.
- Riesgo de ruina por tamaño de bankroll (predictivo y con el winrate en los extremos del IC95 %), bankroll necesario para una ruina de 5 % o menos (o aviso de que ninguno alcanza si la muestra no permite asegurar un winrate positivo), distribución del mayor drawdown y de la ruina dentro de un horizonte, Kelly (completo, fraccionado y con el límite inferior del IC95 %) y regla de subir, mantener o bajar de stake.
- Simulación con puente browniano: la ruina no depende del tamaño del bloque. Se contrastó con la fórmula exacta de ruina y con la del drawdown medio de un movimiento browniano sin deriva.
- Panel web: bloque "Riesgo y bankroll" en el detalle del jugador (bankroll en entradas de 100 bb) y `POST /api/riesgo`.
- 46 pruebas nuevas (314 en total).
- Límites: modelo browniano con manos independientes, sin rachas, cambios de nivel ni rake. Umbrales de 5 % (cómodo) y 15 % (bajar) son convenciones. La regla de subir supone el mismo winrate en bb/100 en el stake superior.

## Fase 2: perfiles de juego
- `poker_analisis/perfiles.py`: clasifica a cada jugador en tight pasivo, tight agresivo, agresivo suelto, estación de llamadas o maniático, a partir de VPIP y de la proporción de agresión postflop (AF = p / (1 - p)).
- Estimación bayesiana: posterior Beta con previa débil de 6-max; devuelve la probabilidad de cada perfil, no solo la etiqueta. El perfil es provisorio con menos de 100 manos, con menos de 80 % de probabilidad o con menos de 30 acciones postflop; con menos de 30 manos no se emite perfil.
- Informe por rival: qué estadísticas lo definen (con intervalo creíble) y cómo explotarlo. Los ajustes puntuales (c-bet, 3-bet, showdown, robo de ciegas) salen solo de estadísticas con 100 o más oportunidades.
- Panel web: el detalle del jugador muestra el perfil, sus probabilidades y los ajustes.
- 27 pruebas nuevas. Umbrales y previas son convenciones del proyecto (constantes al inicio del módulo), no resultados medidos.
- Hallazgo y corrección: los bots "TAG" jugaban cerca del 37 % de las manos (PFR 36 %), o sea agresivos sueltos. Se recalibró el umbral preflop de 0,55 a 0,60 (`simulacion.UMBRAL_TAG`): ahora juegan cerca del 21 % y salen tight agresivos con dos semillas distintas. Los pasivos son estaciones de llamadas (VPIP 94 %, sin subir nunca) y el aleatorio es maniático. Para reproducir resultados viejos: `simular_mesa(..., umbral_tag=0.55)`. Las cifras de evaluación del modelo de rangos en README y docs se midieron con el bot anterior y no se recalcularon.

## Fase 5: informe por bloques de 1000 manos
- `poker_analisis/bloques.py`: resultado (bb/100 con intervalo, bb/100 ajustado por EV de all-ins, probabilidad de winrate positivo), proceso contra la guía, 3 leaks de mayor costo con manos para repasar, evolución entre bloques, proyección y objetivo del próximo bloque.
- Panel web: pestaña "Bloques de 1000"; el informe del jugador principal se calcula solo al cargar las manos (segundo plano, con avance) y se puede copiar como texto. Los ejemplos de cada leak abren la mano en el repaso.
- `POST /api/bloques`; `jugador_principal` en `/api/estado`.
- 36 pruebas nuevas (240 en total): EV de all-in con manos de resultado exacto conocido, proyección, partición, ejemplos y coincidencia de cifras con el panel.
- Límites: el ajuste por EV cubre solo all-ins de dos jugadores con ambas manos visibles; las bb perdidas valoran solo desvíos donde la guía calcula el EV de igualar.

## v2.3 (2026-10-22) - Fase 1: estadísticas completas
- `poker_analisis/estadisticas_completas.py` (`CalculadorCompleto`): cada estadística se guarda como éxitos y oportunidades,
  con intervalo de Wilson al 95 % y alerta de muestra (menos de 30 oportunidades: insuficiente; menos de 100: baja).
- Preflop: VPIP y PFR por posición (UTG, MP, CO, BTN, SB, BB), 3-bet, 4-bet, fold a 3-bet, robo de ciegas y defensa de la
  ciega grande (se retira, iguala o 3-bet).
- Postflop: c-bet en el flop, segunda y tercera apuesta (turn y river), fold a cada una, check-raise por calle, donk bet,
  factor de agresión por calle, WTSD, W$SD y apuestas de river que pierden en el showdown (solo ve los faroles pagados).
- Resultado: bb/100 con intervalo, por profundidad de stack y por cantidad de rivales en el flop; rake atribuido a las manos ganadas.
- Contraste: sobre 3.000 manos simuladas, VPIP, PFR, 3-bet, c-bet, fold a c-bet, WTSD, W$SD, bb/100 y su intervalo dan
  exactamente lo mismo que el calculador anterior. 19 pruebas nuevas (204 en total), con manos construidas a mano.
- Panel web: el detalle del jugador muestra las estadísticas completas (con un solo stake) y la alerta de muestra en texto.
- Pendiente de Fase 1: bb/100 ajustado por EV de los all-ins (se hace junto con el informe por bloque de la Fase 5) y los
  rangos de referencia, que necesitan fuentes confiables antes de usarse como criterio.

## v2.2 (2026-10-22) - Fase 0: base de datos confiable (en curso)
- Importador de texto (`ggpoker.py`): lee la fecha y hora de la cabecera (`ResultadoMano.fecha`), así la curva y el
  drawdown se ordenan cronológicamente también con historiales de texto. Antes quedaban en orden de archivo.
- Verifica que el bote cierre: el bote reconstruido tiene que igualar el "Total pot" del resumen, y cobros + rake tienen
  que sumar ese bote (tolerancia de 1 centavo). Si no cierra, la mano se rechaza con el motivo.
- Jugadores "sitting out" ya no cuentan como que vieron el flop (inflaban las estadísticas).
- Archivos con BOM de UTF-8 y saltos de línea de Windows: ya se leen (con BOM se perdía la primera mano del archivo).
- Una mano con formato inesperado se rechaza con motivo en vez de tumbar toda la carga.
- `scripts/validar_importacion.py`: informe de rechazos por motivo y por archivo, controles de integridad y una muestra
  al azar con el texto original junto a lo que entendió el importador, para revisar a mano.
- `tests/test_ida_vuelta_texto.py`: manos del motor (2 a 6 jugadores, all-in, botes laterales, rake) escritas como
  historial de texto y releídas; todo coincide con el original. 9 pruebas nuevas en total (185 en verde).
- Pendiente de Fase 0: validar con historiales reales del usuario. Hasta entonces el importador sigue "sin validar con
  archivo real"; las pruebas de ida y vuelta solo prueban coherencia interna, no fidelidad a cada sala.

## v2.1 (2026-10-22)
- Panel web local de estudio (`app/web.py`, interfaz en `app/static/`): filtros por jugador, stake, fechas, posición, mínimo
  de manos, métrica y showdown; curva de resultados y drawdown; resultado por posición; tabla de jugadores.
- Repaso acción por acción con una mesa dibujada, cinta de equity de la mano y guía en cada decisión del jugador.
- Video sincronizado: se elige un video local, se marca en qué momento ocurre cada paso (atajo M) y el panel sigue al
  video; tocar un paso lleva el video a su marca. Las marcas se guardan en el navegador y se exportan a JSON.
- Análisis de una situación escrita a mano (cartas, tablero, bote, rivales con rango por porcentaje o manos exactas).
- `poker_analisis/guia.py`: reproduce una mano, estima rangos de los rivales con lo que el jugador veía, calcula equity
  multiway por Monte Carlo y sugiere fold, check, call, bet o raise con sus razones. No usa las cartas de los rivales.
- Pensado para repasar manos ya jugadas, no para uso en vivo: las salas de poker prohíben la asistencia en tiempo real.
- El servidor solo escucha en 127.0.0.1, valida el encabezado Host y exige JSON en los POST.
- `tests/test_guia.py`: 17 pruebas (rangos, decisiones, reproducibilidad, no usar cartas ajenas, API y seguridad).

## v2.0 (2026-10-21)
- Panel en streaming: `analizar_manos` acepta un iterable (un generador) y procesa las manos en una sola pasada.
  Nuevo `CalculadorEstadisticas` (`estadisticas.py`): `agregar(mano)` de a una y `resultados()`. `calcular` queda
  como envoltorio con la misma salida. Por jugador se guardan dos arreglos de doubles (netos en bb y fecha), no las manos.
  `iterar_directorio` (`real.py`) genera las manos de a una; `cargar_directorio` sigue devolviendo lista.
- Verificado: el panel dio la misma tabla que v1.9 para 2.500 manos simuladas con dos stakes (36 filas, salida idéntica).
- Fecha de la mano: `ResultadoMano.fecha`, desde `year`, `month`, `day` y `time` del PHH (hora sin zona = UTC).
  El drawdown del panel se calcula en orden cronológico cuando todas las manos de un stake tienen fecha.
- `jugada_en` se guarda en la carga. Las manos ya cargadas no se actualizan (la carga es `on conflict do nothing`).
- Carga con COPY: `carga.cargar_copy` (tablas temporales + inserción por conjuntos). `scripts/cargar_supabase.py` lo usa.
  Medido en PostgreSQL 16 local con 3.000 manos: `executemany` 1.228 manos/s; COPY 3.911 manos/s (x3,2).
  Mismo contenido y repetir la carga no duplica (`tests/test_carga_postgres.py`).
- Ventana: el análisis corre en un hilo; la tabla se actualiza cuando termina.
- `equity_rangos`: el mazo base se arma una vez, no en cada iteración. Mismo resultado con la misma semilla
  (20.000 iteraciones: 1,30 s -> 0,58 s).
- `riesgo.prob_ruina_simulada`: menos trabajo por paso, misma salida (3.000 trayectorias: 3,5 s -> 2,9 s).
- Pruebas: 159 (146 + 11 nuevas en `tests/test_fecha.py` + 2 de PostgreSQL, que requieren `POKER_DSN_PRUEBA`).
- Importador de texto en streaming: `ggpoker.iterar_directorio`; el panel ya no acumula manos con ningun formato.
- Nuevo: `scripts/completar_jugada_en.py` completa `jugada_en` en manos PHH ya cargadas (solo donde es nulo,
  repetible). Probado contra PostgreSQL 16: 50 manos actualizadas, 0 en la segunda corrida.
- Pendientes: validar el parser de texto con un historial real; rotar la clave de la base de prueba;
  el importador de texto no trae fecha (`jugada_en` queda nulo para ese formato).

## v1.9 (2026-10-21)
- Rendimiento: `evaluar_mejor` ya no enumera las 21 combinaciones de 5 cartas; cuenta valores y palos una vez
  y decide la categoria directamente (unas 20 veces mas rapido: ~4 us frente a ~80-100 us por mano). Devuelve
  exactamente la misma tupla: se verifico con 220.000 manos (60.000 al azar y 160.000 sesgadas a escaleras,
  colores y fulls) y con la simulacion publicada (2.000 manos, semilla 7: resultados identicos).
  La version lenta queda como `evaluar_mejor_referencia` para las pruebas.
- Efecto medido: equity heads-up de ~6.500 a ~87.000 iteraciones/s; simulacion de mesa de ~34 a ~500 manos/s.
- Correccion: `cargar_directorio` (PHH y texto) ordenaba los archivos como texto (`1, 10, 2`) y no recorria
  las subcarpetas en orden. Ahora usa orden natural (`phh.clave_natural`). Afecta a la validacion temporal.
- Correccion: `carga.literalizar` generaba `inf` (SQL invalido) con stacks infinitos; ahora `'Infinity'`.
- Carga: los jugadores se envian una vez por lote, no una por asiento y mano.
- Esquema: se elimina el indice redundante `acciones_mano_idx` (lo cubre `unique (mano_id, orden)`).
  Para una base ya creada: `drop index if exists poker.acciones_mano_idx;` (ya incluido en schema.sql).
- Higiene: sin imports sin usar (pyflakes limpio). README actualizado (estado, estructura, tiempos, pruebas).
- Sin cambios: W$SD sigue con distinta definicion segun la fuente (documentado en el README).
- Pruebas: 146 (8 nuevas: equivalencia del evaluador, orden de carga, literalizar). Suite: 97 s -> 52 s.
- Pendientes: validar el parser de texto con un archivo real, procesar manos en streaming, carga con COPY,
  guardar `jugada_en`, rotar la clave de la base de prueba.

## v1.8 (2026-10-21)
- Nuevo: `docs/04_documento_tecnico_final.md` (Etapa 8): estado por requisito, resultados con datos reales,
  calibracion, limitaciones, riesgos, seguridad y hoja de ruta a produccion.
- Medido: latencia de inferencia (mediana 0,05 ms, p99 0,10 ms) y cobertura de pruebas (88 % total; motor 90 %, evaluador 100 %).
- Sin cambios en el codigo del sistema. Pruebas: 138.

## v1.7 (2026-10-21)
- Nuevo (RF-06): `poker_analisis/equity_rangos.py`. `equity_contra_rango` calcula la equity de una mano
  contra un rango (distribucion sobre las 169 manos canonicas), con correccion por cartas conocidas;
  `equity_contra_modelo` la calcula contra el posterior de `ModeloRangos`. Reproducible con semilla.
- Nuevo: `scripts/equity_rango.py` (linea de comandos).
- Pruebas: 138. Referencias: KK vs AA ~18 %, AA vs KK ~82 %, AA vs mano aleatoria ~85 %.
- Hallazgo con Pluribus (10000 manos): la recalibracion por temperatura no mejora el ECE de los primeros
  pliegues (T entre 1.00 y 1.10); se mantiene como opcion, no por defecto.

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
