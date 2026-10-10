# Consistency issues

Clashes found between specs, the roadmap (`specs/README.md`) and `CLAUDE.md`.
Status: `open` → `resolved` (record how).
**Type:** *decision* = needs the user's call · *order* = roadmap sequencing · *gap* = something no spec covers · *change* = a change to something already built (list every affected spec, file and test).
Spec numbers in the "Clash" column are from the roadmap version where the issue was found. The "Resolution" column uses current numbers.

## Open

_None._ New findings go here as:

| ID | Type | Clash | Proposed fix |
|---|---|---|---|

## Resolved

| ID | Clash | Resolution |
|---|---|---|
| ISSUE-001 | End trip blocks posts vs. offline queue loses moments | Accept items taken before the end (09.3). |
| ISSUE-002 | "Every member appears" vs. "no invented events" | Rule removed from CLAUDE.md; the story follows the posts. |
| ISSUE-003 | Who can end the trip? | Creator only; `members` gets a creator role. Also covers wrapping up parts (02.1, 02.3, 09.2, 09.3, 09.7). |
| ISSUE-004 | Can a photo have a caption? | Post = optional text + up to 5 photos/videos (03.1 `post_media`, 08.2, 06.2). |
| ISSUE-005 | Capture time/location spec came after the endpoints using it | Folded into 03.1/03.2; the separate capture-time spec (numbered 03.6 at the time) was dropped. |
| ISSUE-006 | Test setup came after specs needing tests | Moved into 01.1 (pytest) and 01.3 (throwaway DB). |
| ISSUE-007 | Sharing built before outbox, so rework | Outbox is now feature 07, sharing is 08 and goes through it. |
| ISSUE-008 | Story job changes end-trip after it's built | 12.1 explicitly "extends 09.6". |
| ISSUE-009 | Timeline order? | Upload time, newest first (03.7, 06.1). |
| ISSUE-010 | Story chapters didn't link to posts, which 13.2 needs | 11.6 chapters list their source moments (see ISSUE-031). |
| ISSUE-011 | Who owns video frame extraction? | 11.4 extracts frames; 10.2 only accepts images. |
| ISSUE-012 | Rate limits handled in two places | 10.4 retries; 11.5 caps parallel calls. |
| ISSUE-013 | Trip status values undefined | Defined in 02.1. |
| ISSUE-014 | Story language? | Always English (11.6, CLAUDE.md). |
| ISSUE-017 | Story starts at trip end vs. late posts still uploading | Wait until no phone holds moments taken before the cut-off, or the creator forces it. Done per part since ISSUE-037 (09.4–09.7, 12.1, 13.1). |
| ISSUE-018 | No limit on items per post | Max 5 items; videos 5 s + 1 s buffer (ISSUE-026); photos shrunk on the phone (03.1, 03.5, 08.2, 08.5). |
| ISSUE-020 | Timeline by upload time vs. story chronology | Not a clash: the timeline uses upload time, and the story uses capture time (11.2). Made explicit. |
| ISSUE-021 | CLAUDE.md said "never assume a language" vs. English-only story | CLAUDE.md now says posts may be in any language; the story is English. |
| ISSUE-015 | Where does the backend run? | Locally for now (phones on the same Wi-Fi). Hosting is decided before the first real trip. |
| ISSUE-019 | Gallery video longer than 5 s | The person trims it themselves, outside the app (phone's gallery/editor). The app refuses videos over the limit (5 s + 1 s buffer) with a message (08.2). |
| ISSUE-016 | How the app loads members-only media | Signed links valid ~24 h (03.8); the app caches by media ID (06.2). |
| ISSUE-022 | A member who never reports blocks the story | The creator decides: 09.7 shows who's still holding moments, and the creator can start anyway (09.6). |
| ISSUE-025 | Signed links expire after ~24 h vs. the story being read days later (13.2) | The parts & stories endpoint (12.4) signs links fresh each time it's called. |
| ISSUE-024 | In-app trimming might need a native module that Expo Go can't load | Not needed: trimming happens outside the app (ISSUE-019), so Expo Go stays. |
| ISSUE-026 | Phone and server video-length checks could disagree (a 5.03 s clip) | One limit with a 1 s buffer: anything ≤ 6.0 s is accepted. Defined in 03.5; 08.2 uses the same values. |
| ISSUE-027 | 08.3 recorded video vs. "no recording feature in the app" | The camera takes photos only (08.3); videos come only from the gallery (08.2). |
| ISSUE-028 | One capture time per post vs. up to 5 items taken at different times | Each item has its own taken time (03.1); a text-only post's time is when it was written. Items are placed in the story and assigned to parts individually (ISSUE-031, 033). |
| ISSUE-029 | Friends could see half-uploaded posts | Posts become visible when complete (03.6); the timeline shows complete posts only (03.7); the story only uses complete posts (11.2); the poster sees "uploading 2/3" (08.6). Timeline "upload time" = when the post became complete. |
| ISSUE-030 | No maximum text length | 2,000 characters, checked on the phone (08.1) and the server (03.1/03.2). |
| ISSUE-031 | Per-item times stored but unused; story placed whole post at earliest item | Story works on *moments*: each photo/video placed at its own time, with its post's text (11.2, 11.3, 11.5, 11.6). |
| ISSUE-032 | Location per post vs. items taken in different places | Location stored per item, read from the photo itself; falls back to where the post was written (03.1, 08.4). |
| ISSUE-034 | Screenshots/forwards have no real taken time | Use the gallery or added time, marked as an estimate (03.1, 08.4). |
| ISSUE-035 | Shrinking (08.5) wipes the photo's hidden time/location | 08.4 reads them from the original first and sends them as separate fields. |
| ISSUE-036 | Phone local time vs. server time | The phone converts all times to UTC before sending (08.4). |
| ISSUE-033 | "End trip" was final vs. wanting "to be continued" stories mid-trip | **Parts**: the creator wraps up a part anytime; the trip stays open and the next part starts automatically; End trip wraps up the final part. Moments go to parts by taken time. Parts continue each other ("Previously…" / "To be continued…"). A full-trip story comes after the final part. Items taken after the trip ends are dropped from their post with a note (09.1–09.7, 11.2, 11.7, 11.11, 12.1, 12.4, 13.4). |
| ISSUE-037 | "Every outbox empty" may never happen while the trip continues | Phones report the taken time of their oldest waiting moment (09.4). A part is ready when no phone holds moments from before its cut-off, or when the creator forces it (09.6). |
| ISSUE-038 | Moments arriving after their part's story is written end up in no story | The full-trip story is written from all moments, reusing saved descriptions (11.3, 11.11). Part stories aren't rewritten. |
| ISSUE-039 | Full-trip story started right after a forced final part, so late moments missed every story | The full-trip story has its own ready rule: no phone holds moments from the trip, or the creator forces it (09.6, 09.7, 12.1, 13.1). |
| ISSUE-040 | ~30 endpoints (02–12) + the app's API client (04.2) had no shared conventions | New spec 01.4 API conventions: `/api/` prefix, one error shape `{"error": {"code", "message"}}`, ISO-8601 UTC times, string IDs. `/health` stays at the root. Every endpoint spec is checked against 01.4. |
| ISSUE-041 | Found while building 01.1: the spec named `httpx` for the test client, but the current Starlette/FastAPI test client warns that `httpx` is deprecated and asks for `httpx2` | Spec 01.1 updated to `httpx2` before changing code; the dev dependency was swapped. Tests run without warnings. |
| ISSUE-042 | Found while writing 01.2: the Gemini SDK reads `GEMINI_API_KEY` from the shell environment itself, so a key kept only in `backend/.env` (loaded into `Settings`) would never reach it | 10.1 passes the key from `Settings` to the Gemini client explicitly (roadmap updated). |
| ISSUE-043 | Found while building 01.2: the test fixture hid `GEMINI_API_KEY` by name, so a future third-party key with its own standard name (added by a later spec) would leak into tests | The fixture now reads every variable name from `Settings` itself, so new settings are isolated automatically (`backend/tests/conftest.py`). |
| ISSUE-044 | Separate folder settings for data (01.3), media (03.3) and the checkpoint store (12.3) could drift apart and break photo links | User chose **one** setting, `STORYMAKER_DATA_DIR`: the database, `media/` and the checkpoint store all live inside it (01.3, 03.3). 01.2's note updated via rule 5 (doc only). |
| ISSUE-045 | (change) Built 01.3 stored `applied_at` as `…+00:00` with microseconds vs. 01.4's one format `…Z` with milliseconds | 01.3's `db.py` now uses `utc_now_iso()`; Changes entry in 01.3; format test added; all tests pass. |
| ISSUE-023 | CLAUDE.md layout said "one tiny spec per feature" vs. features split into specs | Layout line fixed. |
