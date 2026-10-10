# Specs roadmap

Each **feature** is split into small **specs**. A spec is one workable step you can
build and check in one sitting. Spec files live at `specs/<feature>/<id>-<slug>.md`,
e.g. `specs/02-trips/02.3-create-trip-endpoint.md`. Open clashes are tracked in `specs/ISSUES.md`.

Status: `proposed` (roadmap line only) → `written` (spec file exists, awaiting approval) → `approved` → `done`.
A built spec that's being changed goes `done` → `changing` → `done` (CLAUDE.md rule 5).

## Terms

- **Item:** one photo or video.
- **Moment:** one item together with its post's text, or a text-only post. The story is built from moments.
- **Part:** a stretch of the trip with its own story. Parts are wrapped up by the creator ("to be continued…").

## Product decisions so far

**Posts**
- A trip can be anywhere, with any group size; posts can be in any language.
- **Post** = optional text (max **2,000 characters**, same check on phone and server) + up to **5** items, with at least one of the two (ISSUE-004, 018, 030).
- Each item keeps **its own taken time and location**, read by the phone from the *original* file before shrinking, and sent as separate fields in universal time (UTC). Items with no reliable time (screenshots, WhatsApp forwards) get the gallery/added time, marked as an estimate (ISSUE-028, 032, 034, 035, 036). A text-only post's time is when it was written.
- **Videos are 5 s max, with a 1 s upload buffer**: anything up to **6.0 s** is accepted, using the same check on the phone and the server (ISSUE-018, ISSUE-026). **Photos are shrunk on the phone** before upload.
- **No video recording in the app.** The in-app camera takes photos only; videos come from the gallery (ISSUE-027).
- **The app never trims videos.** A gallery video over the limit (5 s + 1 s buffer) is refused, with a message asking the person to trim it in their phone's own gallery/editor and pick it again (ISSUE-019).

**Timeline**
- **Friends only see a post once all its items have uploaded.** The poster sees their own as "uploading 2/3" (ISSUE-029).
- The **timeline** is ordered by upload time, newest first, where upload time is when the post became complete (ISSUE-009, 029).
- Media is served through **signed links valid ~24 h**; the app caches media by its ID (ISSUE-016).

**Parts & ending the trip**
- Only the **creator** wraps up parts and ends the trip (ISSUE-003).
- The creator can **wrap up a part** anytime. The trip stays open, posting continues, and the next part starts automatically. **End trip** wraps up the final part (ISSUE-033).
- Each moment belongs to the part whose time window contains its **taken time**, so one post can span two parts (ISSUE-031, 033).
- After the trip ends, items **taken before the end** are still accepted. Items taken after the end are dropped from their post, with a note to the poster (ISSUE-001, 033).
- A part's story starts once **no phone still holds moments taken before the part's cut-off**, or when the **creator forces it**. Nobody is waited for automatically; the creator sees who's still holding moments (ISSUE-017, 022, 037).

**Stories**
- **Each part gets its own story**, placing every moment at its own taken time, even if that splits one post across chapters (ISSUE-031).
- Parts **continue** each other: a non-final part ends with "To be continued…", and the next opens with a short "Previously…" recap (ISSUE-033).
- After the final part, a **full-trip story** is written from **all moments** of the trip, reusing saved descriptions, so moments that arrived too late for their part's story still make it in. Part stories are never rewritten (ISSUE-033, 038). The full-trip story **waits until no phone holds any moments from the trip**, or the creator forces it (ISSUE-039).
- Stories are always written in **English** (ISSUE-014). There's no rule that every member must appear; the story follows the posts (ISSUE-002).

**Setup**
- The backend runs **locally** for now; hosting for real trips is decided later (ISSUE-015).

## v1: trips, sharing, parts, stories

### 01 Backend foundation
| Spec | What | Status |
|---|---|---|
| 01.1 | Project setup: `uv`, FastAPI app, `GET /health`, pytest + test client, git repo ([spec](01-backend-foundation/01.1-project-setup.md)) | done |
| 01.2 | Settings from the environment + `.env.example` ([spec](01-backend-foundation/01.2-settings-from-env.md)) | done |
| 01.3 | SQLite database + numbered migrations (tests use a throwaway DB) ([spec](01-backend-foundation/01.3-database-and-migrations.md)) | done |
| 01.4 | API conventions: `/api/` prefix, one JSON error shape, ISO-8601 UTC times, string IDs (ISSUE-040) ([spec](01-backend-foundation/01.4-api-conventions.md)) | done |

### 02 Trips (backend)
| Spec | What | Status |
|---|---|---|
| 02.1 | `trips` table (incl. status values) + `members` table (incl. creator role) | proposed |
| 02.2 | Join-code generator (short, unique, easy to type) | proposed |
| 02.3 | Create-trip endpoint (caller becomes creator) | proposed |
| 02.4 | Member token auth (header → current member) | proposed |
| 02.5 | Join-trip endpoint | proposed |
| 02.6 | Get-trip endpoint (name, members, status) | proposed |

### 03 Posting (backend)
| Spec | What | Status |
|---|---|---|
| 03.1 | `posts` table (text ≤ 2,000 chars, written time & location, expected item count, complete flag) + `post_media` table (max 5 per post, each with its own taken time (UTC, estimate flag) and location) | proposed |
| 03.2 | Create-post endpoint (text, written time & location, how many items will follow) | proposed |
| 03.3 | Media storage on disk in `<data dir>/media/` (safe names, type and size checks) | proposed |
| 03.4 | Add a photo to a post + thumbnail | proposed |
| 03.5 | Add a video to a post + thumbnail frame; defines the length limit (5 s + 1 s buffer → ≤ 6.0 s accepted) | proposed |
| 03.6 | Mark a post complete when its last item arrives (text-only posts are complete at once) | proposed |
| 03.7 | Timeline endpoint (complete posts only, with their media, newest completed first) | proposed |
| 03.8 | Serve media via signed links (~24 h expiry); timeline returns signed links | proposed |

### 04 Mobile foundation
| Spec | What | Status |
|---|---|---|
| 04.1 | Expo + TypeScript app that runs in Expo Go | proposed |
| 04.2 | API client (base URL, token header, errors) | proposed |
| 04.3 | Remember member token & trip on the device | proposed |
| 04.4 | Navigation shell: welcome vs. trip | proposed |

### 05 Create & join (mobile)
| Spec | What | Status |
|---|---|---|
| 05.1 | Create-trip screen | proposed |
| 05.2 | Join-trip screen | proposed |
| 05.3 | Share invite code via share sheet | proposed |

### 06 Timeline (mobile)
| Spec | What | Status |
|---|---|---|
| 06.1 | Timeline list with text posts (newest first) | proposed |
| 06.2 | Posts with up to 5 photos/videos (album view; cache by media ID, not by link) | proposed |
| 06.3 | Who posted it: names + member colors | proposed |
| 06.4 | Pull-to-refresh + auto-refresh | proposed |

### 07 Outbox (mobile, offline-first): built before sharing so every upload goes through it
| Spec | What | Status |
|---|---|---|
| 07.1 | Local outbox: save a post and its media on the device first | proposed |
| 07.2 | Uploader: create the post, then upload each media item; retries when back online | proposed |
| 07.3 | Show "waiting for signal" posts in the timeline | proposed |

### 08 Sharing (mobile)
| Spec | What | Status |
|---|---|---|
| 08.1 | Compose a post: text field (max 2,000 chars, same check as 03.2) + send (into the outbox) | proposed |
| 08.2 | Add photos/videos from the gallery (max 5; videos over 6.0 s refused with a "trim it in your gallery first" message; same check as 03.5) | proposed |
| 08.3 | Take a photo with the camera (no video recording) | proposed |
| 08.4 | Read each item's taken time & location from the original (before 08.5 shrinks it), convert to UTC, flag estimates | proposed |
| 08.5 | Shrink photos before they go into the outbox | proposed |
| 08.6 | Upload status per post (queued / uploading 2/3 / sent / failed, with the reason, e.g. "taken after the trip ended") | proposed |

### 09 Parts & ending the trip
| Spec | What | Status |
|---|---|---|
| 09.1 | `parts` table (wrapped parts: number, cut-off time; the open part is the next number) + which part a moment belongs to (by taken time) | proposed |
| 09.2 | Wrap-up-part endpoint: creator only; cut-off = now; the next part opens automatically | proposed |
| 09.3 | End-trip endpoint: creator only; wraps up the final part; later, items taken after the end are dropped from their post with a note | proposed |
| 09.4 | Outbox-status endpoint: each phone reports the taken time of its oldest waiting moment (or "nothing waiting") | proposed |
| 09.5 | Mobile: report outbox status whenever it changes | proposed |
| 09.6 | Ready rule + status endpoint, for a part (no phone holds moments taken before its cut-off) and for the full trip (no phone holds any moments from the trip); the creator can force either; lists who's still holding moments | proposed |
| 09.7 | Mobile: creator's "Wrap up this part" and "End trip" buttons + confirm; shows who's still uploading; "start story now" and "write full-trip story now" | proposed |

### 10 LLM helper (backend)
| Spec | What | Status |
|---|---|---|
| 10.1 | Gemini 2.5 Flash call returning a Pydantic object (API key passed from `Settings` explicitly, ISSUE-042) | proposed |
| 10.2 | Accept images as input (callers supply them) | proposed |
| 10.3 | Mock mode for tests | proposed |
| 10.4 | Retry on errors and rate-limit responses | proposed |

### 11 Story agent (backend, LangGraph)
| Spec | What | Status |
|---|---|---|
| 11.1 | Graph skeleton: state + stub nodes, runs end to end | proposed |
| 11.2 | Load-moments node: the part's moments (complete posts split into moments, taken time inside the part's window), ordered by taken time | proposed |
| 11.3 | Describe-moment node: one photo (or video frames) with its post's text, or a text-only post; saves each description for reuse | proposed |
| 11.4 | Video frame extraction (a few frames from each short clip) | proposed |
| 11.5 | Describe all moments in parallel, capped at N at a time | proposed |
| 11.6 | Write-story node in English (title, chapters that list their source moments, ending) | proposed |
| 11.7 | Continuity: Part 2+ opens with a "Previously…" recap of the earlier part; non-final parts end with "To be continued…" | proposed |
| 11.8 | Review node (grounded in the moments? chronology right?) | proposed |
| 11.9 | Revise loop (max 2 rounds) | proposed |
| 11.10 | Save the part's story | proposed |
| 11.11 | Full-trip story: from all moments of the trip (reuses saved descriptions; describes late arrivals first), then review & save | proposed |

### 12 Story jobs (backend)
| Spec | What | Status |
|---|---|---|
| 12.1 | `jobs` table + start a part's story job when the part is ready (extends 09.6); start the full-trip job when the final part's story is saved and the full trip is ready (09.6) | proposed |
| 12.2 | Job-status endpoint (step, done, error) | proposed |
| 12.3 | Checkpointing: retry resumes where it failed | proposed |
| 12.4 | Parts & stories endpoint: each part's status and story, plus the full-trip story (freshly signed photo links) | proposed |

### 13 Story screen (mobile)
| Spec | What | Status |
|---|---|---|
| 13.1 | Progress view per part and for the full trip: "waiting for uploads" → "writing Part 2…" / "writing the full trip…" | proposed |
| 13.2 | Story reader: chapters with their moments' photos | proposed |
| 13.3 | Error + try-again | proposed |
| 13.4 | Parts list: Part 1, Part 2, …, Full trip | proposed |

## After v1: video

One video per part (ending "to be continued…") plus a full-trip video, made from the stories.
Before writing video specs, decide how to generate them: a free slideshow,
Gemini-styled stills (~$0.50/video), open-source models (need a GPU), or paid
image-to-video (~$3–10+/video).
