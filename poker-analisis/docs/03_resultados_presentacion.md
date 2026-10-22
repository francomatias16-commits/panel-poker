# Resultados del análisis estadístico de Texas Hold'em No Limit

Documento de resultados para la presentación. Todas las cifras salen de los scripts del proyecto y se pueden reproducir con los comandos indicados.

## 1. Qué se construyó

Un sistema en Python con cinco piezas, que se validaron por separado:

1. **Evaluación de manos y equity** (`evaluador.py`, `equity.py`): ranking de manos de 5 a 7 cartas, equity Monte Carlo con error estándar, probabilidad exacta de mejora en flop y turn, y outs. Verificado contra las 2.598.960 manos posibles de cinco cartas.
2. **Motor de partida** (`motor.py`): blinds, apuestas, all-in, botes laterales y reapertura de apuestas. Cada mano se verifica por conservación de fichas. Prueba de estrés: 2.000 manos aleatorias.
3. **Estadísticas de jugador** (`estadisticas.py`): VPIP, PFR, 3-bet, AF, WTSD, W$SD y bb/100 con intervalo de confianza del 95 %.
4. **Inferencia de rangos** (`rangos.py`): distribución bayesiana sobre las 169 manos preflop, que se actualiza con cada acción del rival. Incluye posición y rivales que entraron como contexto, y calibración de probabilidades.
5. **Importador de manos reales** (`phh.py`, `real.py`): formato PHH para Pluribus, WSOP y HandHQ. Cada mano se valida y las que no cumplen se rechazan con motivo.

## 2. Simulación controlada

Mesa de 6 jugadores, 100 BB de stack, blinds 1/2, con perfiles de referencia de estilo conocido. Como la simulación conoce todas las cartas, el modelo de rangos se puede contrastar con lo que realmente pasó.

**Predicción de acciones preflop** (4.000 manos, 1.000 de prueba):

| Perfil | Logloss modelo | Logloss base | Mejora | Acierto top-1 |
|---|---|---|---|---|
| TAG-1 | 0,823 | 0,910 | 9,6 % | 66 % |
| TAG-2 | 0,837 | 0,931 | 10,1 % | 66 % |
| TAG-3 | 0,812 | 0,897 | 9,5 % | 67 % |
| Pasivo-1 | 0,136 | 0,140 | 2,7 % | 97 % |
| Pasivo-2 | 0,159 | 0,163 | 2,7 % | 96 % |
| Aleatorio | 1,125 | 1,123 | −0,2 % | 46 % |

**Lectura.** El modelo aprende los perfiles con estilo consistente, y no inventa información donde no la hay (en el aleatorio la mejora es nula). Los pasivos casi no se pueden mejorar porque su base ya es casi determinista.

**Calibración.** Con 20.000 manos, el error de calibración (ECE) baja a 0,012 con escalado de temperatura. La calibración isotónica pura empeoraba al aleatorio, y mezclada con la predicción original no aportó con esa muestra, así que no se usa.

**Contexto de posición y rivales** (logloss absoluto, TAG-1 / Pasivo-1):

| Variante | TAG-1 | Pasivo-1 | ECE |
|---|---|---|---|
| Base | 0,822 | 0,123 | 0,014 |
| Con posición | 0,786 | 0,093 | 0,011 |
| Posición + rivales que entraron | 0,766 | 0,096 | 0,017 |

La posición mejora la predicción de forma consistente. Los rivales que entran mejoran más a los TAG, pero empeoran la calibración porque hay menos datos por celda.

**Advertencia.** Los bots tienen umbrales fijos y ajustan su rango según la posición, así que estas mejoras son un caso favorable construido en la simulación.

## 3. Manos reales de Pluribus (10.000 manos, dataset público)

Pluribus es un bot de referencia de 6 jugadores, con blinds 50/100. Las 10.000 manos cuadran (suma de netos cero en cada una) y no hay rechazos.

| Jugador | Manos | VPIP | PFR | bb/100 | ±IC95 |
|---|---|---|---|---|---|
| MrBlue | 9.121 | 31,4 % | 18,8 % | +16,5 | ±18 |
| Eddie | 5.510 | 27,2 % | 17,6 % | +12,2 | ±25 |
| Budd | 2.509 | 25,1 % | 18,1 % | +28,7 | ±36 |
| MrOrange | 7.512 | 20,8 % | 14,3 % | −12,1 | ±18 |
| Gogo | 488 | 31,8 % | 22,7 % | −57,2 | ±99 |

**Lectura.** Con este número de manos, ningún jugador se distingue de cero: los intervalos cubren desde ganancias grandes hasta pérdidas grandes.

**Modelo de rangos sobre estas manos.** La mejora sobre la base es de 0,1 a 0,9 %, muy lejos del 10 % de la simulación. **Conclusión central: la ventaja medida con bots no se transfiere a jugadores reales**, porque los humanos son menos deterministas y el base por perfil ya captura buena parte de lo predecible.

## 4. Muestra de HandHQ (online, 2009, 25 a 1.000 NL)

Muestra de 25 archivos por nivel, con cerca de 20.000 manos válidas por nivel.

| Nivel | VPIP | PFR | 3-bet | AF | Mediana neto/mano (bb) |
|---|---|---|---|---|---|
| 1.000 NL | 26,4 % | 17,6 % | 6,9 % | 2,61 | −3,10 |
| 100 NL | 24,8 % | 14,1 % | 5,5 % | 2,48 | −5,00 |
| 25 NL | 22,1 % | 10,1 % | 3,0 % | 3,32 | −3,00 |

**Lectura.** El VPIP y el PFR caen a medida que baja el nivel, así que los jugadores más altos entran con manos más selectas. La mediana de neto por mano (−2 a −5 bb) es el rake implícito del dataset, que no registra el rake por separado.

**Advertencias de la muestra.**
- Las cartas están casi todas ocultas, así que sirve para estadísticas de acciones y resultados, no para evaluar el modelo de rangos.
- El neto medio está arrastrado por unas 20 manos de cada 20.000 con pérdidas mayores de 200 bb. Por eso se reporta la mediana.
- Se rechazan entre 4 % y 20 % de las manos según el nivel. Los motivos son: sin resultado registrado (la mayoría), y registros donde el total cobrado supera lo invertido en el bote (254 manos en 1.000 NL, de las cuales 231 son botes sin ninguna subida). El filtro deja fuera un tipo de bote concreto, así que la muestra lo subrepresenta.

## 5. Conclusiones para la presentación

1. **El sistema funciona técnicamente.** Motor con conservación de fichas, evaluación verificada exhaustivamente, importador validado con tres fuentes de manos reales y 83 pruebas automáticas.
2. **La predicción de acciones aprende lo que tiene estructura.** Con bots de estilo fijo mejora el logloss cerca de 10 %; con posición y contexto, mejora más.
3. **La ventaja no se transfiere a humanos.** Con manos reales, la mejora sobre la base es de 0,1 a 0,9 %. Es el hallazgo más importante para una lectura honesta de la predicción.
4. **Las métricas de rentabilidad necesitan muchas manos.** Con 10.000 manos, el intervalo de bb/100 es de ±18 a ±99. Distinguir estilos de forma confiable requiere del orden de 100.000 manos.
5. **Los datos históricos tienen sesgos documentados.** HandHQ no registra cartas ni rake, y sus registros no siempre cuadran. Se rechazan con motivo, y se informa cuántos.

## 6. Limitaciones y trabajo pendiente

- Los bots son perfiles de referencia, no humanos. Su postflop usa equity con pocas iteraciones (60), por velocidad.
- No se modela rake, torneos, historia entre manos ni tilt.
- El modelo de rangos todavía no usa las acciones postflop de los rivales ni su historial.
- Omaha queda fuera de la demo (ver `docs/01_alcance_etapa0.md`).
- Pendientes de licencia: validar la licencia del dataset PHH (CC BY 4.0 para datos, MIT para código) y revisar AGPL si se incorpora TexasSolver.

## 7. Fuentes y atribución

- Dataset PHH, Juho Kim (Universidad de Toronto), CC BY 4.0. Repositorio `uoftcprg/phh-dataset` (código MIT). Zenodo 13997158.
- Los datos reales no se modifican; el proyecto no los incluye (pesan 17 GB).

## 8. Cómo reproducir

```
python3 -m unittest tests.test_cartas tests.test_evaluador tests.test_equity tests.test_phh tests.test_handhq tests.test_real tests.test_motor tests.test_estadisticas tests.test_rangos
python3 scripts/simular.py 3000 7
python3 scripts/evaluar_rangos.py 20000 11
python3 scripts/evaluar_contexto.py 4000 11
python3 scripts/analizar_real.py /ruta/al/phh-dataset/data/pluribus
python3 scripts/analizar_handhq.py /ruta/al/phh-dataset/data/handhq 25
```
