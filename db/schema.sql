-- Esquema para Supabase (PostgreSQL). Cada resultado se traza a su fuente (RNF-04).
-- Todo vive en el schema `poker`, que la API de Supabase no expone, para no mezclarse con `public`.
-- Los montos están en la unidad de la fuente (centavos en GGPoker).
-- Seguridad: RLS activado y sin políticas. Solo el rol de servicio accede; los nombres de
-- jugadores se seudonimizan antes de llegar acá (ver poker_analisis/almacen.py).

create schema if not exists poker;

create table if not exists poker.fuentes (
    id           bigint generated always as identity primary key,
    nombre       text not null unique,        -- 'pluribus', 'handhq', 'ggpoker-propio'
    licencia     text not null,               -- 'CC BY 4.0', 'propio'
    formato      text not null,               -- 'phh', 'ggpoker-txt'
    importada_en timestamptz not null default now()
);

create table if not exists poker.jugadores (
    id         bigint generated always as identity primary key,
    fuente_id  bigint not null references poker.fuentes(id),
    seudonimo  text not null,                 -- hash con sal; nunca el nombre real
    unique (fuente_id, seudonimo)
);

create table if not exists poker.manos (
    id           bigint generated always as identity primary key,
    fuente_id    bigint not null references poker.fuentes(id),
    mano_ref     text not null,               -- identificador de la mano en la fuente
    archivo      text,                        -- archivo de origen (trazabilidad)
    jugada_en    timestamptz,
    n_jugadores  smallint not null check (n_jugadores between 2 and 10),
    blind_chico  numeric not null check (blind_chico > 0),
    blind_grande numeric not null check (blind_grande >= blind_chico),
    boton        smallint not null check (boton >= 0),
    tablero      text not null default '',
    unique (fuente_id, mano_ref)
);

create table if not exists poker.asientos (
    id               bigint generated always as identity primary key,
    mano_id          bigint not null references poker.manos(id) on delete cascade,
    asiento          smallint not null check (asiento >= 0),
    jugador_id       bigint references poker.jugadores(id),
    stack_inicial    numeric not null check (stack_inicial >= 0),
    neto             numeric not null,        -- ganado menos invertido, en fichas
    cartas           text,                    -- null si están ocultas
    vio_flop         boolean not null default false,
    llego_showdown   boolean not null default false,
    gano_showdown    boolean not null default false,
    unique (mano_id, asiento)
);

create table if not exists poker.acciones (
    id        bigint generated always as identity primary key,
    mano_id   bigint not null references poker.manos(id) on delete cascade,
    orden     integer not null check (orden >= 0),
    calle     text not null check (calle in ('preflop', 'flop', 'turn', 'river')),
    asiento   smallint not null check (asiento >= 0),
    tipo      text not null check (tipo in ('f', 'cc', 'cbr')),
    monto     numeric,
    unique (mano_id, orden)
);

create index if not exists asientos_jugador_idx on poker.asientos(jugador_id);
-- unique (mano_id, orden) ya indexa mano_id; el índice acciones_mano_idx era redundante.
drop index if exists poker.acciones_mano_idx;

alter table poker.fuentes   enable row level security;
alter table poker.jugadores enable row level security;
alter table poker.manos     enable row level security;
alter table poker.asientos  enable row level security;
alter table poker.acciones  enable row level security;

revoke all on all tables in schema poker from anon, authenticated;
revoke usage on schema poker from anon, authenticated;
