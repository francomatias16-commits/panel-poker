# Etapa 0: Documento de alcance y criterios de éxito

## Estado
Borrador. Pendiente de aprobación y de recibir muestras de historial.

## Objetivo
Construir un sistema de análisis estadístico para Texas Hold'em y Omaha a partir de historiales de mano exportados. El sistema importa datos, construye perfiles de jugadores, estima rangos y probabilidades de acción calibradas, y simula partidas en un entorno propio.

## Restricción operativa
El sistema no se conecta a salas de terceros, no opera en tiempo real sobre mesas reales y no asiste decisiones en partidas con dinero real.

## Alcance
- Variantes: Texas Hold'em (No Limit, cash, 6-max y 9-max).
- Fuera de alcance de la demo: Omaha. Queda documentado como extensión futura. El evaluador de manos se diseña para poder incorporarla sin reescribir el núcleo.
- Fuente de datos: historiales de mano exportados por el titular de la cuenta.
- Motor de partida: simulado, con bots de perfiles configurables.

## Fuentes de datos

La fuente principal pasa a ser un conjunto de datasets públicos documentados, complementados por tres insumos:

1. **Datasets públicos** (académicos y de usuarios): análisis de comportamiento.
   - **Candidato verificado, Hold'em**: dataset PHH (Juho Kim, Universidad de Toronto, repositorio uoftcprg/phh-dataset y Zenodo 13997158). Licencia CC BY 4.0. Formato PHH. Unas 21,6 millones de manos de Hold'em No Limit de 2009 (cash online), más 10.000 manos de Pluribus y 83 de un final de WSOP 2023. Advertencia: los datos son de 2009 y su comportamiento puede no representar el juego actual.
   - **Omaha**: fuera de alcance de la demo (decisión del 20/10/2026). No hay dataset público verificado.
2. **Solvers de referencia** (TexasSolver, short deck y Hold'em, no Omaha): frecuencias de equilibrio para calibrar la estrategia. No modelan humanos. Licencia AGPL v3: uso personal libre, pero integrar el código en otro software o publicarlo como servicio requiere licencia comercial. Requiere revisión legal antes de usarlo en una entrega institucional. Se considera solo como referencia externa, no como dependencia del código.
3. **Simulación propia con verdad de terreno**: bots con perfiles conocidos, donde se sabe qué tenía cada jugador. Permite validar la inferencia antes de usar datos reales.
4. **Historial propio del titular**: sirve como prueba de formato y caso de estudio. Ya no es el único insumo.

Regla de uso: la inferencia se valida primero con simulación propia y después con datasets públicos.

## Pendientes para cerrar la Etapa 0
1. Confirmar licencia y procedencia del dataset PHH antes de incorporarlo como insumo oficial.
2. Revisión legal de AGPL v3 si se decide usar algún solver en la entrega institucional.
3. Formato del historial propio, si se decide incluirlo (sala y versión de exportación).
4. Audiencia de la presentación (interna o externa).
5. Stakes a incluir en el análisis.
6. Tamaño mínimo de muestra por jugador para reportar perfiles.

## Criterios de éxito (provisionales)
- El parser reconoce el 100 % de las manos de la muestra o reporta explícitamente las que rechaza.
- El evaluador de manos coincide con las frecuencias combinatorias teóricas.
- Las probabilidades de acción están calibradas sobre datos reservados (curva de calibración cercana a la diagonal).
- Las simulaciones son reproducibles con la misma semilla.
- Cada reporte documenta supuestos, muestra e incertidumbre.
