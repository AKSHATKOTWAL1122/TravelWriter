-- Spec 02.7: a member on a new phone asks to get back in as themselves (ISSUE-047).

CREATE TABLE rejoin_requests (
    id          TEXT PRIMARY KEY,
    member_id   TEXT NOT NULL REFERENCES members (id),
    -- Hash of the new phone's token, never the token itself (ISSUE-055).
    -- Approval (spec 02.8) moves it onto the member; until then it opens nothing.
    token_hash  TEXT NOT NULL UNIQUE,
    status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'declined', 'replaced')),
    created_at  TEXT NOT NULL,
    closed_at   TEXT,
    -- closed_at is set if and only if the request is no longer pending.
    CHECK ((status = 'pending') = (closed_at IS NULL))
);

-- At most one pending request per member; asking again replaces it (ISSUE-054).
CREATE UNIQUE INDEX rejoin_requests_one_pending_per_member ON rejoin_requests (member_id) WHERE status = 'pending';
