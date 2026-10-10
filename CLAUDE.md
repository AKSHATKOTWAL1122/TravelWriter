# StoryMaker

A group travel app. Friends on a trip (any trip, anywhere) each share text, photos and
short videos (5 s max, plus a 1 s upload buffer) from their phones as it happens. The trip can be wrapped up in **parts**
("to be continued…"): for each part, an AI agent writes a story from everyone's posts,
and when the trip ends it also writes a full-trip story. Later, a second agent turns the
stories into videos in a style the group picks (anime, watercolor, …).

The app is **destination-agnostic**. Never hardcode or assume a route, place, country
or group size. Posts may be in any language; the story is always written in English. Example trips in specs and tests should vary.

## How we work

1. **Spec first.** No code without an approved spec in `specs/`.
2. **Features are split into small specs.** A feature (e.g. "02 Trips") is broken into
   several workable specs (02.1, 02.2, …). Each spec is one step: about 10–20 lines of goal, behavior
   and acceptance (the consistency-check and changes sections don't count), buildable and checkable in one sitting. Files go in `specs/<feature>/<id>-<slug>.md`;
   use `specs/_template.md`.
3. **One spec at a time:** write it, get approval, build it, check every acceptance item, then move on.
4. **Consistency check, after every spec and during every build.**
   - After writing a spec, compare it with **every** other spec, `specs/README.md` and this file.
     Look for clashes in names, data fields, ordering and dependencies, behavior, and scope overlap.
   - While building, compare the code against **all** specs, not just the current one.
   - Log every finding in `specs/ISSUES.md` (ID, what clashes with what, proposed fix, status),
     fill in the spec's "Consistency check" section, and point it out to the user.
   - Product decisions go to the user as questions. Don't resolve them silently.
5. **Changes to built specs get the same check.** When the user wants to change something already built:
   - Before touching code, check the change against **every** spec **and the existing code and tests**.
     List every spec, file and test it affects, plus any clashes it would create.
   - Log it in `specs/ISSUES.md` as type *change* (what changes, what it affects, proposed plan)
     and point it out to the user, even if the change looks small.
   - Update the spec(s) first: status `changing`, plus a line in the spec's "Changes" section.
     Get approval, then change the code.
   - Re-run the tests and acceptance checks of **every** affected spec, not just the changed one,
     then mark them `done` again.
   - Never patch code without updating its spec.
6. **Build only what the spec says.** Put ideas in the spec's "Later" line, not in code.
7. **Ask when unclear.** Don't guess product decisions.
8. When a spec is done, tick its acceptance boxes and mark it `Status: done` in `specs/README.md`.
9. **Git:** build each spec (or change) on its own branch, `spec/<id>-<slug>`. Once all its acceptance
   checks pass, commit with the message `<id>: <title>` and merge into `main`. `main` only holds finished work.
   Before every push, run the repo audit (`python3 scripts/audit.py --rev main`, spec 00.1) **and** all tests
   (backend and audit). Push `main` to GitHub (`origin` = https://github.com/AKSHATKOTWAL1122/TravelWriter,
   a **public** repo) only if both pass. The audit also scans for secrets and local files (`.env`, databases).
   If the format of the roadmap, issues log or spec files changes, update `scripts/audit.py` in the same change.

## Stack

| Part | Choice |
|---|---|
| Mobile app | Expo (React Native) + TypeScript; dev testing via Expo Go |
| Backend | Python 3.12+, FastAPI, managed with `uv` |
| Agents | LangGraph |
| LLM | Gemini 2.5 Flash via `google-genai` SDK; model name from env `STORYMAKER_MODEL` (default `gemini-2.5-flash`) |
| Storage (v1) | SQLite + local disk for uploaded media; backend runs locally (phones reach it over the same Wi-Fi). Hosting for real trips is decided later. |
| Video (later) | Not decided yet; see specs/README.md |

## Layout (planned)

```
backend/      FastAPI app, LangGraph agents, tests
mobile/       Expo app
specs/        <feature>/<id>-<slug>.md small specs, README.md (roadmap, decisions, status), ISSUES.md
scripts/      repo tooling: audit.py (run before every push) and its tests
```

## Rules

- Product decisions live in `specs/README.md` ("Product decisions so far"). Follow them.
- Secrets come from the environment (`GEMINI_API_KEY`). Never commit keys; `backend/.env.example` holds names only.
- **Settings:** every backend setting lives in `Settings` (`backend/storymaker/config.py`). A spec that adds one
  adds it there **and** to `backend/.env.example` together. The app's own settings use the `STORYMAKER_` prefix;
  third-party keys keep their standard names. App code reads them via `get_settings()`, never `os.environ`.
  Tests are isolated from real settings automatically (`backend/tests/conftest.py`).
- Stories must be grounded in what people posted: no invented events, people or places.
  (There's no rule that every member must appear; the story follows the posts.)
- **Endpoints follow spec 01.4:** register on `api_router` (`/api/…`), raise `ApiError(status, code, message)`,
  use `storymaker.times` for every time (API and database) and `new_id()` for every ID.
- Every LLM call goes through one small helper, so the model or provider can be swapped in one place.
- Agent code must be runnable without network in tests (mock the LLM helper).

## Commands

Backend (run from `backend/`):

| What | Command |
|---|---|
| Install | `uv sync` |
| Run (reachable from phones on the same Wi-Fi) | `uv run uvicorn storymaker.main:app --host 0.0.0.0 --port 8000 --reload` |
| Test | `uv run pytest` |

Repo (run from the repo root, plain `python3`, no install needed):

| What | Command |
|---|---|
| Audit before pushing | `python3 scripts/audit.py --rev main` |
| Audit tests | `python3 -m unittest discover scripts` |
