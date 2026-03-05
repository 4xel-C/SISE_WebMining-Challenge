-- ============================================================
-- KeySentinel — Supabase / PostgreSQL schema
-- Run this in the Supabase SQL Editor (or via psql)
-- All statements are idempotent (safe to re-run)
-- ============================================================

-- ── Enum type ─────────────────────────────────────────────
DO $$ BEGIN
    CREATE TYPE activitycategory AS ENUM ('coding', 'writing', 'gaming');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── users ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id                 SERIAL PRIMARY KEY,
    name               VARCHAR(128)       NOT NULL UNIQUE,
    is_on_line         BOOLEAN            NOT NULL DEFAULT FALSE,
    on_going_activity  activitycategory   NULL
);

-- ── activities ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS activities (
    id     SERIAL PRIMARY KEY,
    label  activitycategory  NOT NULL UNIQUE
);

-- ── recording_sessions ────────────────────────────────────
CREATE TABLE IF NOT EXISTS recording_sessions (
    id           SERIAL PRIMARY KEY,
    uuid         VARCHAR(64)        NOT NULL UNIQUE,
    user_id      INTEGER            NULL REFERENCES users(id)      ON DELETE SET NULL,
    activity_id  INTEGER            NULL REFERENCES activities(id) ON DELETE SET NULL,
    started_at   DOUBLE PRECISION   NOT NULL,
    ending_at    DOUBLE PRECISION   NULL,
    coding_time  DOUBLE PRECISION   NOT NULL DEFAULT 0.0,
    writing_time DOUBLE PRECISION   NOT NULL DEFAULT 0.0,
    gaming_time  DOUBLE PRECISION   NOT NULL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS ix_recording_sessions_uuid        ON recording_sessions(uuid);
CREATE INDEX IF NOT EXISTS ix_recording_sessions_user_id     ON recording_sessions(user_id);
CREATE INDEX IF NOT EXISTS ix_recording_sessions_activity_id ON recording_sessions(activity_id);

-- ── keyboard_events ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS keyboard_events (
    id                    SERIAL PRIMARY KEY,
    recording_session_id  INTEGER            NOT NULL REFERENCES recording_sessions(id) ON DELETE CASCADE,
    event_type            VARCHAR(16)        NOT NULL,   -- 'key_press' | 'key_release'
    key                   VARCHAR(64)        NOT NULL,   -- e.g. 'a', 'Key.ctrl_l'
    timestamp             DOUBLE PRECISION   NOT NULL,   -- Unix epoch (seconds)
    flight_time           DOUBLE PRECISION   NULL,       -- key_press only
    dwell                 DOUBLE PRECISION   NULL        -- key_release only
);

CREATE INDEX IF NOT EXISTS ix_keyboard_events_recording_session_id ON keyboard_events(recording_session_id);
CREATE INDEX IF NOT EXISTS ix_keyboard_events_timestamp            ON keyboard_events(timestamp);

-- ── mouse_events ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mouse_events (
    id                    SERIAL PRIMARY KEY,
    recording_session_id  INTEGER            NOT NULL REFERENCES recording_sessions(id) ON DELETE CASCADE,
    event_type            VARCHAR(16)        NOT NULL,   -- 'click' | 'move' | 'scroll'
    x                     INTEGER            NOT NULL,
    y                     INTEGER            NOT NULL,
    timestamp             DOUBLE PRECISION   NOT NULL,   -- Unix epoch (seconds)
    button                VARCHAR(32)        NULL,       -- click only, e.g. 'Button.left'
    speed                 DOUBLE PRECISION   NULL,       -- move only, px/s
    scroll_dx             INTEGER            NULL,       -- scroll only
    scroll_dy             INTEGER            NULL        -- scroll only
);

CREATE INDEX IF NOT EXISTS ix_mouse_events_recording_session_id ON mouse_events(recording_session_id);
CREATE INDEX IF NOT EXISTS ix_mouse_events_timestamp            ON mouse_events(timestamp);
