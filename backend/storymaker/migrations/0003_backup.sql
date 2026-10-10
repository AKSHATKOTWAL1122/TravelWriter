-- Spec 02.10: the member the creator picked as backup, who alone decides the creator's
-- own rejoin request (ISSUE-056).

-- 1 for the trip's backup, 0 for everyone else. The creator is never the backup.
ALTER TABLE members ADD COLUMN is_backup INTEGER NOT NULL DEFAULT 0
    CHECK (is_backup IN (0, 1) AND NOT (is_backup = 1 AND role = 'creator'));

-- A trip has at most one backup.
CREATE UNIQUE INDEX members_one_backup_per_trip ON members (trip_id) WHERE is_backup = 1;
