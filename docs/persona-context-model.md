# Persona and context model

What Nexus needs to know to put the right trusted asset in front of someone, and how it shows that the asset was worth it:

> **Who is the user → what are they trying to do now → what should the portal recommend → how do we establish trust → how do we measure adoption.**

This page defines that model: the personas, intents, activities, recommendation types and trust concepts the portal works with. The prototype's code uses these terms as written here. The last section says where each one lives. Anything the prototype holds as sample data, or that MUFG has not yet confirmed, is marked as such.

```text
Recognize me                 Role · Function · Interests · Maturity
        ↓
Understand my intent         Learn · Find · Improve · Ask · Contribute
        ↓
Understand my activity       e.g. for a Relationship Manager: coverage planning, wallet share,
  and objective              client meeting, deal origination, onboarding, credit request,
                             cross-sell, portfolio review
        ↓
Recommend                    Prompts · Agents · Data · People   (and the learning behind them)
        ↓
Establish trust              Identity · Permissions · Governance · Ownership · Accountability · Feedback
        ↓
Launch / use                 in the system where the work happens
        ↓
Learn and improve            feedback, contributions, better recommendations
        ↓
Measure adoption             Discovery · Reuse · Value · Adoption
```

---

## 1. Recognize me

Who the person is. This is stable across a session, and it comes from the directory and Nexus's own records, never from what the person typed.

| Element | What it means | How the portal knows it | Status |
| --- | --- | --- | --- |
| **Role** | The persona they work as | Derived from the directory job title, then department, business unit, then a default. The rule that fired is recorded and shown. | Built. The mapping from real MUFG job titles is sample. |
| **Function** | Where they sit in the bank | Department and business unit, as the directory states them | Built |
| **Interests** | What their role cares about | The persona's domains, capabilities and tags. Interests from behaviour are derived from footprints but are shown, not used for ranking. | Built |
| **Maturity** | How far along they are | Inferred from learning progress: *beginner*, *developing* or *experienced*. It is always labelled as inferred, with the reason. | Built. It needs required learning per role to be meaningful for every persona. |
| **Permissions** | What they are entitled to see | Directory groups | Built |

**Personas today**

| Persona | Who | Activities mapped |
| --- | --- | --- |
| Relationship Manager | Covers corporate clients: plans coverage, prepares meetings, originates deals and takes credit requests through approval | 8 (below) |
| Risk analyst | Investigates fraud, credit risk and disputes. Credit analysts map here for now. | Not yet |
| Compliance user | Owns KYC, AML, policy and regulatory obligations | Not yet |
| Operations user | Runs collections, recovery, servicing and back-office processes | Not yet |
| Business user | Works in a line of business and wants everyday tasks done faster | Not yet |
| Developer | Builds and maintains software and agents on the platform | Not yet |

What someone does *now*, such as the client they are preparing for, belongs to the task (section 3). It is never saved to this profile.

---

## 2. Understand my intent

Why they came. One request can carry more than one intent. "Find me a KYC agent and teach me how to use it" is Find and Learn.

| Intent | They want to | Example | Answered mainly from |
| --- | --- | --- | --- |
| **Learn** | Build skill or understanding | "Find a course on IFRS 9" | Learning |
| **Find** | Locate a prompt, agent, system or data to do the work | "Find a prompt for a covenant scan" | Prompts, Discover, systems of record |
| **Improve** | Do a task they already do faster, with AI | "Make my portfolio review faster" | Prompts, Discover |
| **Ask** | Reach a person or get a question answered | "Who can help with a credit request?" | Community, named experts |
| **Contribute** | Share or write something for others to reuse | "Share a prompt I use for account plans" | Prompt library, Create |

When a request names the kind of thing it wants ("an agent", "a course", "an expert"), that narrows where the portal looks.

Greetings, thanks, goodbyes and "what can you do?" are conversation, not intents. They are answered directly, and "what can you do?" is answered with these five intents.

---

## 3. Understand my current activity and objective

What they are doing right now. This is built per request and lives for the conversation only.

| Element | What it means |
| --- | --- |
| **Activity** | The job the request belongs to, from the persona's mapped activities |
| **Objective** | What they are trying to achieve, in their own words |
| **Needs** | What that job needs: data, people, tools |
| **Subject** | The client or deal the request names, e.g. "Preparing for: Starbucks". It is kept for this conversation only: not in the profile, not in logs. |
| **Sensitivity** | Public, internal, client confidential or confidential. It decides what may be sent where (section 5). |

A follow-up that names no job or client ("And who owns it?") stays on the one the conversation was already on.

**Relationship Manager activities**

| Activity | Objective | Where the work happens |
| --- | --- | --- |
| Coverage planning | Plan coverage for the quarter | Salesforce, Customer 360, client profitability |
| Wallet-share analysis | Estimate the client's wallet and MUFG's share of it | Client profitability, market intelligence, Salesforce |
| Client meeting preparation | Prepare for a client meeting | Customer 360, market intelligence, Salesforce |
| Deal origination | Shape a financing proposal | Market intelligence, Salesforce, credit system |
| Client onboarding | Onboard a new client | Konect, Customer 360, Salesforce |
| Credit requests | Take a credit request through approval | Credit system, client profitability, Customer 360 |
| Cross-sell | Find the next product for a client | Customer 360, client profitability, Salesforce |
| Portfolio reviews | Review the book | Client profitability, credit system, Salesforce |

Each activity lists its steps, the systems of record, and what helps at each intent. The portal points to where the work happens; it does not replace those systems.

---

## 4. Recommend

What the portal puts in front of someone. It is ordered by what they came for, then by the rest of the activity, and adjusted for their maturity: learning comes earlier for a beginner and later for someone experienced.

| Type | What it is | Where it comes from |
| --- | --- | --- |
| **Prompts** | Validated prompt templates, each with inputs, guidelines and a sample output | Prompt library: 60 prompts from three desks, plus 4 templates (sample data) |
| **Agents** | Approved AI agents that do a task end to end | Discover (the agent marketplace) |
| **Data** | Systems of record and data products | The asset catalogue |
| **People** | Experts, communities, forums and FAQs | The asset catalogue and Community |
| *Learning* | The courses and guides behind the job | Learning: hub content plus the licensed-catalogue courses (sample data) |

Only what the person may see is ever recommended. Nothing is shown that the catalogue does not hold.

---

## 5. Establish trust

Why someone can rely on what they are shown.

| Element | What it covers | In the portal | Status |
| --- | --- | --- | --- |
| **Identity** | Who is asking | Sign-in; the directory profile | Built (demo sign-in in the prototype) |
| **Permissions** | Who may see and use what | Directory groups decide what is visible, in every pillar. High-risk prompts are shown only to their own desk. | Built |
| **Governance** | Rules on data and use | Each request is classified by sensitivity. A data policy says what the approved model may receive for each class: as typed, with client details masked, or nothing. Searches and logs always get the masked form. | Built. The policy values are prototype defaults, to be confirmed by MUFG's data policy. |
| **Ownership** | Who stands behind an asset | Every asset has a trust card: owning team and person, purpose, who can use it, how to get access. | Built. Blank fields show "To be confirmed" until the owner confirms them. |
| **Accountability** | Who approved it and why it was recommended | Approval and date on the trust card. Each answer carries "How this was chosen": the role and rule, the intent, the activity, the policy applied, and what each pillar was asked. | Built. Approvals are to be confirmed per asset. |
| **Feedback** | Telling owners what works | "Was this helpful?" on each answer and each asset. Contributions are reviewed before they go live (Data Privacy Office for prompts, Model Risk for agents, as the design reference states). | Captured. Routing to owners is to be confirmed. |

---

## 6. Launch / use

Assets open where the work happens: the system of record, the agent's page in Discover, a prompt copied into the approved model, a course in its provider's catalogue. Where an owner has not confirmed a launch link, the portal says so rather than guessing one.

## 7. Learn and improve

- **Feedback:** each answer and each asset records whether it helped.
- **Contributions:** Create takes a prompt (three steps, ending in a data safety declaration), a skill video or an agent proposal, and holds it for review.
- **Drafting:** the assistant can draft a new prompt from validated ones, carrying their constraints forward.

---

## 8. Measure adoption

| Measure | Question it answers | Signal captured today | Status |
| --- | --- | --- | --- |
| **Discovery** | Are people finding assets? | Every answered request, with its intents, activity and the pillars asked; searches and views across pillars | Captured |
| **Reuse** | Do they use what they find? | What was opened from each answer; saves; launches | Captured. Live "uses" per prompt are sample figures until connected to the approved model. |
| **Value** | Is it worth it? | "Was this helpful?"; hours saved per use as stated by each contributor | Partly. Measured time saved is not captured. |
| **Adoption** | Is it spreading? | Distinct users and repeat use by persona and activity, derived from the above | Derivable. No report or target yet. |

Telemetry holds ids and measures, never the question or the client.

---

## How the prototype uses this model

```text
Request
  → Conversation        small talk and "what can you do?" answered directly
  → Guardrails          permissions, sensitivity, data policy                   (Establish trust)
  → Understand          intents, activity, objective, needs                     (Intent, Activity)
  → Policy on the plan  allowed pillars and jobs, what each pillar is asked     (Establish trust)
  → Pillars             prompts, agents, learning, people, in parallel          (Recommend)
  → Reply               from the catalogue, or written by the model within policy
  → Telemetry           ids and measures                                        (Measure adoption)
```

| Concept | Where it lives |
| --- | --- |
| Personas, role interests | `backend/data/personas.json` |
| Role mapping from the directory | `backend/data/persona-mapping.json`, `backend/app/identity.py` |
| Recognize me (UserContext, maturity) | `backend/app/context/user.py`, `backend/app/context/models.py` |
| Intents | `backend/app/journeys/intent.py` |
| Activities, needs, what helps at each intent | `backend/data/journeys.json` |
| Data, people, prompts, use cases (trust cards) | `backend/data/assets.json` |
| Prompt library | `backend/data/prompts.json` |
| Current activity (TaskContext) | `backend/app/journeys/models.py`, `backend/app/hub/graph.py` |
| Data policy | `backend/data/policy.json`, `backend/app/hub/guardrails.py` |
| Conversation | `backend/app/hub/conversation.py` |
| Telemetry | `hub_sessions` table, `backend/app/hub/telemetry.py` |

## To confirm with MUFG

- The persona mapping for real directory job titles, and the activities of each persona beyond the Relationship Manager.
- The data policy: what the approved model may receive at each sensitivity.
- Owners, approvals and access routes on each asset's trust card.
- Where feedback on an asset is routed, and who acts on it.
- Which adoption measures matter, and their targets.
