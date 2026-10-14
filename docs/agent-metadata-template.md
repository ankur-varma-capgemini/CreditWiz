# Agent Metadata Template

The canonical model every agent in Nexus is described with. It is what the marketplace displays, searches and curates on. The machine-readable version is `backend/data/agent-metadata-template.json`.

## Structure

```text
IDENTITY
├─ id                  stable slug                              required
├─ name                display name                             required
├─ tagline             one sentence, what it does for the user  required
└─ version                                                       optional

BUSINESS
├─ description         2-4 sentences                            required
├─ problem_solved      why it exists                            optional
├─ business_domains    Onboarding, Compliance, Collections, ... required
├─ use_cases           plain-language tasks                     required
└─ personas            business_user, compliance_user, ...      required

CAPABILITIES
├─ capabilities        what it can do                           required
├─ services            services exposed to other systems        optional
├─ example_tasks       literal prompts                          optional
├─ tags                extra search keywords                    optional
└─ category            carousel family                          derived if omitted

TECHNICAL
├─ platform            AWS Bedrock Agents, Agent 365, ...       required
├─ tools_services      systems it calls                         optional
├─ models              models used                              optional
└─ architecture_pattern  reference pattern name                 optional

GOVERNANCE
├─ owner.team / owner.name / owner.email                        team required
├─ status              production | pilot | beta | in_development | deprecated
└─ access.type / access.how / access.launch_url / access.request_url

RESOURCES
├─ documentation_url                                             optional
├─ architecture_url                                              optional
└─ documents[]: type, system, url (links only, no copies)        optional

LIFECYCLE
├─ created_at          ISO date                                 required
└─ updated_at          ISO date                                 required
```

## What agent owners need to give us first

Only three things to start: **name**, **brief description**, and **whatever metadata already exists**. We fill the template from that and send back the list of gaps.

## Simple intake format (accepted as-is)

Owners who prefer a flat file can send this shape. Nexus normalises it into the canonical model on load, so no conversion step is needed:

```json
[
  {
    "agentId": "agent-001",
    "name": "KYC Verification Agent",
    "description": "Helps validate customer identity and KYC documents.",
    "domain": "Compliance",
    "useCases": ["Customer onboarding", "Identity verification"],
    "capabilities": ["Document validation", "Identity verification", "Compliance checks"],
    "personas": ["Compliance User", "Business User"],
    "platform": "AWS",
    "owner": "KYC AI Team",
    "status": "Production",
    "tools": [],
    "models": [],
    "documentationUrl": "",
    "architectureUrl": "",
    "launchUrl": "",
    "createdDate": "",
    "updatedDate": ""
  }
]
```

Mapping rules: `agentId → id`, `domain → business_domains`, `useCases → use_cases`, `tools → tools_services`, `owner` (string) → `owner.team`, `status` text → canonical status, persona labels → persona ids, `launchUrl → access.launch_url`, `createdDate/updatedDate → created_at/updated_at`. `tagline` defaults to the first sentence of the description; `category` is derived from the domain.

## Where it lives

```text
Agent list from Ganesh / Vinay
        ↓
Populate the template
        ↓
backend/data/agents.json          (static JSON metadata source for the MVP)
        ↓
Hub backend reads and validates   (every record checked against the model)
        ↓
Marketplace: search, carousels, agent detail, actions, feedback
```

For the MVP the metadata source is a static JSON file. That keeps the prototype focused on proving discovery, search, curation and the agent-detail experience without integration dependencies. The source can later be replaced by enterprise registries (Agent 365, AWS Agent Registry, prompt and skill stores) without changing the user experience.
