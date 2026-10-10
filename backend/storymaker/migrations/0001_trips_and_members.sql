-- Spec 02.1: trips and the people in them. IDs and times are TEXT (spec 01.4).

CREATE TABLE trips (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    join_code   TEXT NOT NULL UNIQUE,
    status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'ended')),
    created_at  TEXT NOT NULL,
    ended_at    TEXT,
    -- ended_at is set if and only if the trip has ended.
    CHECK ((status = 'ended') = (ended_at IS NOT NULL))
);

CREATE TABLE members (
    id            TEXT PRIMARY KEY,
    trip_id       TEXT NOT NULL REFERENCES trips (id),
    display_name  TEXT NOT NULL,
    -- Comparison form of display_name, from storymaker.names.name_key().
    name_key      TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('creator', 'member')),
    -- Only a hash of the member's token is stored, never the token itself.
    token_hash    TEXT NOT NULL UNIQUE,
    joined_at     TEXT NOT NULL
);

-- A trip can never have two creators.
CREATE UNIQUE INDEX members_one_creator_per_trip ON members (trip_id) WHERE role = 'creator';

-- Names are unique within a trip, ignoring case in any language (ISSUE-046, ISSUE-049).
CREATE UNIQUE INDEX members_unique_name_per_trip ON members (trip_id, name_key);
