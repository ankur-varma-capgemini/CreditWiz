"""Authored hub navigation and sample announcements. Catalogs live in backend/data."""

from .models import Link, Notification, Pillar, Section, PillarSearch

PILLARS = [
    Pillar(
        id="marketplace",
        number=1,
        title="AI Marketplace and Discovery",
        short_title="Discover",
        card_title="Discover AI",
        description="Find trusted solutions, agents and reusable capabilities.",
        icon="search",
        tone="blue",
        priority=True,
        primary_links=[
            Link(label="AI solutions", href="/marketplace/solutions"),
            Link(label="Agents", href="/marketplace/agents"),
            Link(label="Capabilities", href="/marketplace/capabilities"),
        ],
        secondary_links=[
            Link(label="Search by business domain", href="/marketplace/agents")
        ],
        cta_label="Explore marketplace",
        cta_href="/marketplace",
        search=PillarSearch(
            placeholder='e.g. I need an agent that can review customer onboarding documents',
            action='Find agents',
            examples=[],
        ),
        sections=[
            Section(
                title="AI solutions",
                href="/marketplace/solutions",
                blurb="Approved, production-ready AI solutions you can adopt today.",
            ),
            Section(
                title="Agents",
                href="/marketplace/agents",
                blurb="Reusable agents with owners, SLAs and usage guidance.",
            ),
            Section(
                title="Capabilities",
                href="/marketplace/capabilities",
                blurb="Platform capabilities such as document intelligence, summarisation and search.",
            ),
        ],
    ),
    Pillar(
        id="prompts",
        number=2,
        title="Prompts & Skills Library",
        short_title="Prompts & Skills",
        description="Find reusable prompts and skills.",
        icon="library",
        tone="blue",
        cta_label="Open the library",
        cta_href="/library",
        search=PillarSearch(
            placeholder='e.g. a pitch deck outline for an RFP',
            action='Find prompts',
            examples=['Pitch deck outline', 'Covenant scan', 'Stress test'],
        ),
        sections=[
            Section(
                title="Prompt library",
                href="/library/prompts",
                blurb="Validated prompts from three desks, each with its inputs, guidelines and a sample output.",
            ),
            Section(
                title="Prompt templates",
                href="/library/templates",
                blurb="Four scaffolds that already carry the constraints review looks for.",
            ),
            Section(
                title="My library",
                href="/library/mine",
                blurb="What you saved, and what you submitted for review.",
            ),
        ],
    ),
    Pillar(
        id="learning",
        number=3,
        title="AI Learning and Enablement",
        short_title="Learning",
        card_title="Learning",
        description="Find learning and guidance for your role.",
        icon="graduation",
        tone="teal",
        priority=True,
        primary_links=[
            Link(label="Catalog", href="/learning/catalog"),
            Link(label="Role-based paths", href="/learning/paths"),
        ],
        secondary_links=[
            Link(label="Getting started", href="/learning?path=getting-started"),
            Link(label="Best practices", href="/learning/best-practices"),
            Link(label="Product docs", href="/learning/docs"),
            Link(label="Quick reference", href="/learning/quick-reference"),
        ],
        cta_label="Explore learning",
        cta_href="/learning",
        search=PillarSearch(
            placeholder='Search the catalog, Pluralsight and Microsoft Learn',
            action='Find learning',
            examples=['Sanctions screening', 'KYC', 'Responsible AI'],
        ),
        sections=[
            Section(
                title="Learning catalog",
                href="/learning/catalog",
                blurb="Courses, guides, videos and documentation.",
            ),
            Section(
                title="Role-based paths",
                href="/learning/paths",
                blurb="Curated paths for analysts, engineers, managers and operations.",
            ),
            Section(
                title="Getting started",
                href="/learning?path=getting-started",
                blurb="Your first hour with AI at MUFG.",
            ),
            Section(
                title="Best practices",
                href="/learning/best-practices",
                blurb="How our teams get reliable results.",
            ),
            Section(
                title="Product docs",
                href="/learning/docs",
                blurb="Reference documentation for hub tools.",
            ),
            Section(
                title="Quick reference",
                href="/learning/quick-reference",
                blurb="One-page cheat sheets.",
            ),
        ],
    ),
    Pillar(
        id="intake",
        number=4,
        title="AI Intake and Enablement",
        short_title="AI Requests",
        description="Submit an AI use case.",
        icon="clipboard",
        tone="purple",
        cta_label="Start a request",
        cta_href="/intake/new",
        search=PillarSearch(
            placeholder='e.g. automate chasing clients for missing documents',
            action='Search requests',
            examples=['Use case request', 'Start a request', 'Review queue'],
        ),
        sections=[
            Section(
                title="Start a request",
                href="/intake/new",
                blurb="Describe a use case and route it for review.",
            ),
            Section(
                title="My requests",
                href="/intake/mine",
                blurb="Track the status of use cases you submitted.",
            ),
            Section(
                title="Review queue",
                href="/intake/queue",
                blurb="For reviewers: use cases awaiting a decision.",
            ),
        ],
    ),
    Pillar(
        id="governance",
        number=5,
        title="Governance and Trust Center",
        short_title="Governance",
        description="Find responsible AI guidance.",
        icon="shield",
        tone="teal",
        cta_label="View guidance",
        cta_href="/governance",
        search=PillarSearch(
            placeholder='e.g. can I use customer data with an external model?',
            action='Search guidance',
            examples=['Responsible AI', 'Model inventory', 'Data handling'],
        ),
        sections=[
            Section(
                title="Policies",
                href="/governance/policies",
                blurb="Acceptable use, data handling and model risk policies.",
            ),
            Section(
                title="Responsible AI guidance",
                href="/governance/responsible-ai",
                blurb="Fairness, transparency and human-in-the-loop expectations.",
            ),
            Section(
                title="Model inventory",
                href="/governance/inventory",
                blurb="Every approved model, its owner and its risk tier.",
            ),
        ],
    ),
    Pillar(
        id="knowledge",
        number=6,
        title="Enterprise Knowledge and Context Foundation",
        short_title="Knowledge",
        description="Explore shared enterprise knowledge.",
        icon="database",
        tone="blue",
        cta_label="Explore knowledge",
        cta_href="/knowledge",
        search=PillarSearch(
            placeholder='e.g. where is beneficial ownership defined?',
            action='Search knowledge',
            examples=['Data glossary', 'Context packs', 'Runbook'],
        ),
        sections=[
            Section(
                title="Knowledge sources",
                href="/knowledge/sources",
                blurb="Connected repositories, wikis and document stores.",
            ),
            Section(
                title="Context packs",
                href="/knowledge/context-packs",
                blurb="Curated context bundles for grounding agents.",
            ),
            Section(
                title="Data glossary",
                href="/knowledge/glossary",
                blurb="Shared definitions for business terms.",
            ),
        ],
    ),
    Pillar(
        id="community",
        number=7,
        title="Community and Collaboration",
        short_title="Community",
        card_title="Community",
        description="Ask questions, share knowledge and find experts.",
        icon="users",
        tone="blue",
        priority=True,
        primary_links=[
            Link(label="Forums", href="/community/forums"),
            Link(label="SME directory", href="/community/experts"),
            Link(label="FAQs", href="/community/faqs"),
        ],
        secondary_links=[
            Link(label="Announcements", href="/community/announcements"),
            Link(label="Success stories", href="/community/stories"),
        ],
        cta_label="Open community",
        cta_href="/community",
        search=PillarSearch(
            placeholder='e.g. who is the expert on sanctions screening?',
            action='Search community',
            examples=['SME directory', 'FAQs', 'Success stories'],
        ),
        sections=[
            Section(
                title="Forums",
                href="/community/forums",
                blurb="Ask questions and share what you have learned.",
            ),
            Section(
                title="SME directory",
                href="/community/experts",
                blurb="Find subject-matter experts by domain.",
            ),
            Section(
                title="FAQs",
                href="/community/faqs",
                blurb="Answers to the most common questions.",
            ),
            Section(
                title="Announcements",
                href="/community/announcements",
                blurb="What changed in the hub this month.",
            ),
            Section(
                title="Success stories",
                href="/community/stories",
                blurb="How teams are getting value from AI.",
            ),
        ],
    ),
    Pillar(
        id="insights",
        number=8,
        title="Operational Intelligence and Value Realization",
        short_title="Insights",
        description="Explore adoption and value insights.",
        icon="chart",
        tone="teal",
        cta_label="View insights",
        cta_href="/insights",
        search=PillarSearch(
            placeholder='e.g. which agents saved the most hours this quarter?',
            action='Search insights',
            examples=['Adoption', 'Hours saved', 'Quality and safety'],
        ),
        sections=[
            Section(
                title="Adoption dashboard",
                href="/insights/adoption",
                blurb="Who is using what, and how often.",
            ),
            Section(
                title="Value realisation",
                href="/insights/value",
                blurb="Hours saved, cases resolved and outcomes delivered.",
            ),
            Section(
                title="Quality and safety",
                href="/insights/quality",
                blurb="Evaluation results and incident trends.",
            ),
        ],
    ),
    Pillar(
        id="platform",
        number=9,
        title="AI Hub Platform Enablement",
        short_title="Platform",
        description="Access platform support and services.",
        icon="settings",
        tone="purple",
        cta_label="Open platform",
        cta_href="/platform",
        search=PillarSearch(
            placeholder='e.g. how do I get API access to an agent?',
            action='Search platform',
            examples=['Access management', 'API keys', 'Integrations'],
        ),
        admin_only=True,
        sections=[
            Section(
                title="Access management",
                href="/platform/access",
                blurb="Roles, groups and entitlements.",
            ),
            Section(
                title="Integrations",
                href="/platform/integrations",
                blurb="Connected systems and API keys.",
            ),
            Section(
                title="Settings",
                href="/platform/settings",
                blurb="Hub-wide configuration.",
            ),
        ],
    ),
]

NOTIFICATIONS = [
    Notification(
        id="mvp-marketplace-v1",
        title="Explore the AI Marketplace",
        body="Find agents for your work and request access in a couple of clicks.",
        href="/marketplace",
        created_at="2026-09-08T12:00:00Z",
    ),
    Notification(
        id="mvp-learning-v1",
        title="Follow your learning path",
        body="Work through your role's learning path and track your progress.",
        href="/learning/paths",
        created_at="2026-09-08T12:00:00Z",
    ),
    # Sample activity from the design reference's prompt library.
    Notification(
        id="library-collab-v1",
        title="Sophia Merrill accepted your collaboration request",
        body="On Corporate pitch structurer.",
        href="/library/prompts/p1",
        created_at="2026-09-15T08:00:00Z",
    ),
    Notification(
        id="library-validated-v1",
        title="Data Privacy Office validated your prompt",
        body="Deal screening summary is now live.",
        href="/library/mine",
        created_at="2026-09-15T06:00:00Z",
    ),
    Notification(
        id="library-review-v1",
        title="Kevin Morrow left a 5-star review",
        body="On a prompt you contributed.",
        href="/library/mine",
        created_at="2026-09-14T09:00:00Z",
    ),
]
