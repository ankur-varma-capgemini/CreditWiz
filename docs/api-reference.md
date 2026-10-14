# API reference

Every endpoint in Nexus. Overview and screenshots are in the [README](../README.md).

## Session and mutation rules

All API routes except health and sign-in endpoints require the HttpOnly session cookie. All POST/PUT requests, including sign-in, require `X-CreditWiz-Request: 1`. Browser origins must be in `CREDITWIZ_ORIGINS`. Unknown or hidden resources return 404. Persona overrides require a hub administrator; they do not alter content permissions or the progress account.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/auth/options` | Development demo choices, or production password mode |
| `POST /api/auth/demo` | Development only: `{user_id}` |
| `POST /api/auth/login` | `{email,password}`; creates an eight-hour session |
| `POST /api/auth/logout` | Revokes the session |
| `GET /api/preferences` | Saved default domain and learning-announcement preference |
| `PUT /api/preferences` | `{default_domain,show_learning_reminders}` |
| `POST /api/notifications/read` | Persists read status for the current user |
| `GET /api/access-requests` | Current user's local pending requests |
| `POST /api/access-requests` | `{agent_id,reason}`; one pending request per user/agent |
| `GET /api/learning/recommended` | Uncompleted, eligible role recommendations |

Learning item filters: `path`, `type` (or `docs` for documentation/guide/Confluence), `topic`, `agent`, `status`, `q`, optional admin `persona`. Path results have sequence numbers. The learning landing includes `paths` and `role_paths` with ordered steps, progress counts and next-item links. Progress rejects blocked prerequisites (409), accepts only 0–100, and emits completion events server-side; direct client `learning_complete` events are rejected.

## Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /api/home` | Current user, business domains, the nine pillars with their sections |
| `GET /api/me` | Current signed-in user from SQLite (development seed in `backend/data/user.json`) with the persona derived via `persona-mapping.json` |
| `GET /api/pillars` | Pillars visible to the current user (admin-only pillars filtered) |
| `GET /api/pillars/{id}` | One pillar with its sections, 404 if hidden or unknown |
| `GET /api/notifications` | Notifications for the current user |
| `GET /api/domains` | Business domain filter options |
| `GET /api/search?q=` | Header typeahead. Name and tag matches first, then the same hybrid retrieval, fusion and relevance gate the marketplace uses, so a typed sentence resolves here too. Intent comes from the local lexicon, never Claude, because this fires while the user types. |
| `GET /api/health` | Liveness |
| `GET /api/marketplace/home?persona=` | Personas, domains and persona-ranked carousels |
| `GET /api/marketplace/agents` | All agents, filter by `domain`, `category`, `persona`, `status` |
| `GET /api/marketplace/agents/{id}` | One agent's full metadata (`/related` for similar agents) |
| `POST /api/marketplace/search` | Natural-language search: `{query, persona?, domain?}` |
| `POST /api/context/events` | Interaction footprints from **any** pillar (shared hub layer) |
| `POST /api/context/feedback` | "Did you find what you needed?" from any pillar |
| `GET /api/context/me` | Profile, derived persona and derived interests in one place |
| `GET /api/context/interests` | Weighted topic signals aggregated across pillars |
| `GET /api/context/summary` | Event and feedback counts by pillar |
| `GET /api/marketplace/curation` | Per-component curation score for every agent (explainable ranking) |
| `GET /api/learning/for-agent/{id}?persona=` | Content that teaches an agent, persona-ordered (Learning-owned) |
| `GET /api/learning/curation` | Per-component learning curation score (explainable) |
| `GET /api/marketplace/metadata-template` | The agent metadata template to hand to agent owners |
| `GET /api/knowledge/sources` | The document types and systems that feed Nexus; an agent's `documents` link to its documents by these types |
| `GET /api/marketplace/agents/{id}/learning` | Recommended videos for the agent |
| `GET /api/learning?persona=` | Role-based learning landing sections |
| `GET /api/learning/items` | Learning items of any type, filterable |
| `GET /api/learning/items/{id}` | One item with related items and agents |
| `POST /api/learning/progress` | Record started / in progress / completed |
| `GET /api/learning/my-learning` | Progress counts and topic coverage |

## Marketplace (Swim Lane 1)

The MVP metadata source is a static JSON file: `backend/data/agents.json` (personas in `personas.json`, carousel definitions in `carousels.json`). Records may use the canonical template or the simple camelCase intake format; both are normalised on load. See [agent-metadata-template.md](agent-metadata-template.md). Point `CREDITWIZ_DATA_DIR` at another directory to swap the source. Copy `backend/.env.example` to `backend/.env` and set `ANTHROPIC_API_KEY` to have Claude interpret search requests (`CREDITWIZ_SEARCH_MODEL` picks the model, default `claude-sonnet-5`); without a key a local lexicon does the job. Footprints and feedback are hub-wide, not pillar-owned: every pillar posts to `/api/context/*` and they land in `backend/var/hub.db` in user-scoped events and feedback tables. Architecture: [shared-user-context.md](shared-user-context.md). Ranking and curation: [discovery-and-curation.md](discovery-and-curation.md). Learning pillar: [learning-pillar.md](learning-pillar.md). Full write-up: [swim-lane-1-marketplace.md](swim-lane-1-marketplace.md).

## Routes

`/` home, `/help`, `/settings`, and one route per pillar (`/marketplace`, `/library`, `/learning`, `/intake`, `/governance`, `/knowledge`, `/community`, `/insights`, `/platform`) with section sub-routes such as `/learning/catalog`. The marketplace has real pages: `/marketplace`, `/marketplace/agents`, `/marketplace/agents/{id}`, plus `/docs` and `/architecture` under each agent. Learning includes `/learning/catalog`, `/learning/paths?path=...`, `/learning/best-practices`, `/learning/docs`, `/learning/quick-reference`, `/learning/me` and `/learning/items/{id}`. Legacy video links still resolve. Unknown paths show a not-found page.

Navigation definitions remain in `backend/app/data.py`; authored catalogs live in `backend/data`; all mutable state is in SQLite. Non-MVP pillar pages show explicit planned-state messaging.
