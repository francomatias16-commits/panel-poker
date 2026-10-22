# Decisiones del proyecto

| Tema | Decisión |
|---|---|
| Omaha | No se incluye. Fuera del alcance y del plan. |
| Sitio / formato de historiales propios | **Indefinido.** "GGPoker" fue solo un ejemplo. Mientras tanto se soporta texto estilo PokerStars (cubre PokerStars, GGPoker y similares) y PHH. |
| Audiencia de la presentación | Interna. |
| Dashboard | Aplicación de escritorio (Tkinter, `app/ventana.py`). |
| Base de datos | Supabase (PostgreSQL). Esquema en `db/schema.sql`, schema propio `poker`. **Aplicado** (ver abajo). |
| Umbral de muestra por perfil | La muestra completa: un perfil es suficiente solo si el jugador participó en todas las manos de su stake. El mínimo numérico sigue siendo configurable. |

## Decididas por el equipo técnico (a pedido del titular)

**Sitio de juego.** No hay uno definido. El importador de texto sigue la estructura de PokerStars, de la
que derivan GGPoker y otros sitios, y no está validado con un archivo real de ninguno. Los sitios con
otro formato (por ejemplo 888 o iPoker) requerirían un parser propio y un archivo de ejemplo. Antes de
analizar historiales propios, conviene verificar que los términos del sitio lo permitan.

**Límite de stakes.** Sin tope. Solo Hold'em No Limit de cash, de 2 a 10 jugadores. Cada stake se analiza
por separado y nunca se mezclan niveles. Se excluyen torneos, Omaha, antes y ciegas "small & big".

## Abiertos
- Aprobar formalmente el alcance de la Etapa 0.
- Elegir el sitio y conseguir un archivo de ejemplo (datos personales removidos) para validar el parser.

## Supabase
Esquema aplicado el 2026-10-21 en el proyecto `qirxsezgelzjizixmaek` (región us-east-1), vacío y creado
para este fin, mediante la migración `poker_esquema_inicial`. Las 5 tablas están en el schema `poker`
con RLS activado y sin permisos para `anon` ni `authenticated`: solo accede el rol de servicio.
Los dos proyectos anteriores (otra organización) no se tocaron.

## Carga de datos
Probada el 2026-10-21 con 2 manos sintéticas (luego borradas): 4 jugadores, 5 asientos y 15 acciones,
con suma de netos igual al rake y carga idempotente. No se cargaron datos reales. No se cargan fecha
de la mano (`jugada_en`) ni datos de torneos.
