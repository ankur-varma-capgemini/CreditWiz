# Shared User Context — a horizontal Nexus capability

Each pillar owns its experience. Nexus owns shared user context, interaction data, and eventually cross-pillar personalisation. Personalisation is **not** built inside Swim Lane 1.

## The layer

```text
                              AI HUB
                                │
 ┌──────────┬──────────┬────────┴─────┬──────────┬──────────┐
 │          │          │              │          │          │
Marketplace Learning  Community    Prompts    Skills    other pillars…
 │          │          │              │          │          │
 └──────────┴──────────┴──────┬───────┴──────────┴──────────┘
                              ▼
                  SHARED USER CONTEXT LAYER
                              │
              ┌───────────────┴───────────────┐
              │                               │
       User Profile                    User Footprints
       Role                            Searches
       Persona (derived)               Views
       Department                      Clicks
       Business Unit                   Launches
                                       Learning activity
                                       Feedback
                                       Collaboration
              │                               │
              └───────────────┬───────────────┘
                              ▼
                     Curation / Ranking
                              ▼
                Personalised Nexus Experience
```

## What exists today

| Piece | Where | Owner |
| --- | --- | --- |
| Signed-in directory-style profile | `backend/var/hub.db` (development seeds from `backend/data/user.json`) | Hub |
| Persona mapping | `backend/data/persona-mapping.json` | Hub |
| Persona derivation | `backend/app/identity.py` | Hub |
| Footprint + feedback store | `backend/app/context/store.py` → `backend/var/hub.db` (per-user events and feedback tables) | Hub |
| Shared API | `backend/app/context/router.py` → `/api/context/*` | Hub |
| Shared client | `frontend/src/lib/context.ts` → `track()`, `sendFeedback()` | Hub |
| Agent metadata, search, carousels, agent detail | `backend/app/marketplace/`, `backend/data/agents.json` | Swim Lane 1 |
| Video catalogue | `backend/app/learning/`, `backend/data/learning.json` | Learning pillar |

Nothing about footprints lives under `marketplace/` any more. The old `/api/marketplace/events` and `/api/marketplace/feedback` endpoints still work but are marked deprecated and simply forward into the shared store with `pillar: "marketplace"`.

## The API every pillar uses

```text
POST /api/context/events     { pillar, type, subject_id, subject_type, query, persona, topics[], meta{} }
POST /api/context/feedback   { pillar, context, helpful, subject_id, query, persona, missing }
GET  /api/context/me         profile + derived persona + derived interests + pillars seen
GET  /api/context/interests  weighted topic signals aggregated across pillars
GET  /api/context/summary    event and feedback counts, broken down by pillar
```

Event vocabulary is shared, not per pillar: `search`, `view`, `click`, `launch`, `request_access`, `documentation_click`, `architecture_click`, `collaborate`, `learning_view`, `learning_complete`, `feedback_positive`, `feedback_negative`. Anything pillar-specific goes in `meta`.

Two pillars already write to it. Opening an agent and then opening a learning video produces:

```json
{"pillar": "marketplace", "type": "view",          "subject_type": "agent", "topics": ["Onboarding", "Compliance", ...]}
{"pillar": "learning",    "type": "learning_view", "subject_type": "video", "topics": ["kyc", "document agent", ...]}
```

and `/api/context/me` returns one context with `pillars_seen: ["learning", "marketplace"]`.

## MVP scope

```text
agents.json
personas.json
user.json            (mock directory profile)
persona-mapping.json
        ↓
Swim Lane 1 curation   ← uses the DERIVED PERSONA only
        ↓
interactions.jsonl     ← collected, nothing reads it for ranking
```

`GET /api/context/interests` shows what the collected data would support. We added it to make the future transition cheap; it was not asked for:

```text
User: u-1001
Base persona: Compliance User   (derived from job title "Compliance Analyst")

Interests
  kyc                 1.00   3 events   marketplace, learning
  document ingestion  0.84   2 events   learning
  compliance          0.55   1 event    marketplace
```

**This is our implementation seam, not a client requirement, and not personalisation.** No ranking code reads it. Swim Lane 1 curation still uses the derived persona alone, which is what was agreed.

## The future, once the value is proven

```text
                ALL 9 PILLARS
                     │
                     ▼
             Event Collection            ← exists today (shared)
                     │
                     ▼
          Shared User Context Store      ← SQLite hub.db, user-scoped
                     │
                     ▼
         Personalization / Curation      ← future, hub-owned
                     │
                     ▼
                ALL 9 PILLARS
```

Worked example, deliberately out of scope for the MVP:

```text
Learning     → reads "Building KYC Agents"
Marketplace  → searches "document validation"
Prompts      → opens a KYC extraction prompt
Architecture → views the document ingestion pattern
        ↓
one user context, not four profiles
        ↓
Marketplace surfaces  KYC Agent, Document Ingestion Agent, Contract Analyzer
Learning surfaces     Advanced KYC Agent Development, Document Ingestion Patterns
```

## Replacing the store

`backend/app/context/store.py` has two functions that touch storage, `_append` and `_read`. Point them at DynamoDB, Postgres or an event bus and no pillar changes. The API contract and the frontend `track()` call stay identical.
