# Migrations

Database tables are created and changed only through files in this folder (spec 01.3).

- Name files `NNNN_<what>.sql`, e.g. `0001_trips_and_members.sql`, numbered in the order they must run.
- Plain SQL, without `BEGIN`/`COMMIT`: each file runs in its own transaction, added automatically.
- Never edit a migration that has already been applied. Add a new numbered file instead.
- Applied migrations are recorded in the `schema_migrations` table and never run twice.
