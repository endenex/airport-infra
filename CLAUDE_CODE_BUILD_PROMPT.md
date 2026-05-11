# Initial Claude Code Build Prompt — Airport Infrastructure Intelligence Platform

> **How to use this.** Paste the prompt below into Claude Code at the start of your first build session. The brief itself (`PLATFORM_BRIEF_v4_LOCKED.md`) must be in your working directory before you start; Claude Code will read it as its first action.
>
> The prompt is intentionally long. It is not the brief — it is the instructions for how Claude Code should orient to the brief, what to do first, what to confirm before coding, and what protocols to follow throughout. Resist the urge to shorten it. The friction at the start prevents drift over months of building.

---

## The prompt

```
You are joining me as the engineering collaborator on a long-running build. We are
constructing a global airport infrastructure intelligence platform. The canonical
reference for everything is PLATFORM_BRIEF_v4_LOCKED.md in this working directory.

== FIRST ACTIONS (do these in order, do not skip) ==

1. Read PLATFORM_BRIEF_v4_LOCKED.md completely. Pay particular attention to:
   - Section 1 (Product identity — what we are and explicitly are not)
   - Section 5 (Data architecture — verified accessibility map)
   - Section 7 (Build sequence — phases and gate criteria)
   - Section 8 (Engineering principles — non-negotiable)
   - Section 12 (Decisions locked — do not relitigate)
   - Section 13 (Decisions rejected — do not propose)
   - Appendix A (Verified data source URLs and known LEIs/CIKs)
   - Appendix C (Claude Code handoff: first 30 days)

2. After reading, summarise back to me in 5-8 bullet points:
   - What we are building (one sentence)
   - The three analytical lenses
   - The six analytical surfaces (just names)
   - The build phase we are starting in and its gate criteria
   - The four non-negotiable engineering principles
   - The data sources you understand are verified accessible
   - Anything in the brief that surprises you or seems internally inconsistent

   This is not a comprehension test. It is alignment verification. If your summary
   reveals you have misread the brief, we fix it before any code is written.

3. Tell me what dependencies, secrets, or external accounts you need from me before
   you can start coding. At minimum I expect you to ask for:
   - Anthropic API key (for LLM extraction pipelines)
   - Companies House API key (UK)
   - EDINET v2 Subscription-Key (Japan)
   - GitHub repository access
   - Database hosting decision (recommend Supabase or Neon — I will choose)
   - Object storage (recommend Cloudflare R2 — I will confirm)

   Do not assume any of these are configured. Ask me to provide each one and tell
   me precisely where to put it (.env file, repository secret, etc.).

4. Propose a sequencing for the first week's work. Do not start coding yet. Your
   proposed sequence should follow Appendix C of the brief (Week 1 — Repository
   and foundation scaffolding) but I want to see your version before you begin,
   so I can correct anything you have misread.

== WORKING PROTOCOL ==

These rules apply to every session, not just this one.

PROTOCOL 1 — Flag tensions, do not silently choose.
When the brief is ambiguous, contradictory, or under-specified for a decision you
need to make, stop and ask me. Do not pick the option that seems most plausible
and proceed silently. The cost of asking is small; the cost of silent drift over
months is large.

PROTOCOL 2 — Locked decisions are locked.
Section 12 of the brief contains 16 locked strategic decisions. Section 13 contains
rejected alternatives. Do not propose alternatives to locked decisions. Do not
revive rejected ones. If you think a locked decision is wrong, you may say so once
and ask me to reconsider; if I confirm, the decision stays locked and we do not
revisit it.

PROTOCOL 3 — Schema versioning is non-negotiable.
Every data record carries a methodology version. No exceptions. If you find
yourself writing a schema without a version field, stop and add it. The brief
anticipates regulatory transitions (CORSIA 2027, ReFuelEU phases) and we must be
able to retain old records under their original methodology while new records use
updated methodology. Retrofitting this later is painful; designing it in is cheap.

PROTOCOL 4 — Provenance is non-negotiable.
Every record carries source_url, source_document_id, retrieved_at, and (for derived
values) calculation_lineage. Customers will challenge specific numbers. We defend
them with full audit trail. If you write an ingestor that stores values without
provenance, you are introducing technical debt that I will have to pay later.

PROTOCOL 5 — LLM confidence scoring on every extraction.
Every LLM-extracted record carries a confidence score. High-confidence
auto-populates the database. Low-confidence queues for my review. The thresholds
are tunable; the scoring itself is mandatory. Cross-validation against alternative
sources (XBRL vs PDF, multiple news sources, etc.) is the foundation of the
LLM-native architecture being a competitive advantage rather than a liability.

PROTOCOL 6 — Assumption sets are first-class objects.
Calculation engines must be architected with assumption sets as first-class objects
from day one, even though the user-facing Assumption Laboratory UI ships in Phase 4.
Do not hardcode cost-of-debt assumptions, traffic recovery trajectories, or any
other modeling parameter as constants. Make them overridable via assumption_set
parameter on every calculation function. Retrofitting this is painful; designing
it in is manageable.

PROTOCOL 7 — API-first internal architecture.
Build internal APIs first; any future UI consumes those APIs. Customer-facing API
ships in Phase 3, but the internal architecture must already be API-shaped before
then. No tight coupling between data layer and presentation layer.

PROTOCOL 8 — Idempotent ingestion.
Re-running an ingestor against the same source yields the same output. No state
drift. No accidental duplication. Use deterministic record IDs derived from source
plus retrieval date plus content hash.

PROTOCOL 9 — Editorial repository is separate.
The editorial product (Substack content, named-voice writing) lives in a separate
repository with a separate deployment lifecycle. Do not mix editorial content with
platform code.

PROTOCOL 10 — Skills before writing.
Before you write any code that creates, reads, or manipulates a file format, view
the relevant SKILL.md under /mnt/skills/public/. In particular:
- /mnt/skills/public/xlsx/SKILL.md (SBTi targets database, ESMA XBRL packages)
- /mnt/skills/public/pdf-reading/SKILL.md (annual reports, prospectuses)
- /mnt/skills/public/file-reading/SKILL.md (general routing)

The skills encode environment-specific knowledge that is not in your training data.
Reading them costs nothing and prevents avoidable mistakes.

== SPECIFIC DO-NOT-DO LIST ==

Things to avoid without explicit founder permission:

- Do not add Playwright or browser automation. The brief's verified workarounds
  cover the major Cloudflare blockers (Schiphol via Contentful CDN, Fraport via
  AEM URL pattern, Auckland via NZX/AnnualReports.com aggregators).
- Do not add real-time data feeds (bond pricing, live market data). Out of scope.
- Do not build any frontend in Phase 1. Backend only until Month 6.
- Do not add features outside the six analytical surfaces in Section 2 of the brief.
- Do not deviate from stack defaults in Section 8 without telling me first.
- Do not skip methodology-versioning architecture, even for "simple" tables.
- Do not use AI to generate editorial content. The named-voice is the moat; AI
  destroys it.
- Do not manually curate the transaction database. Use the LLM-native pipeline.
  Manual curation is what Inframation does; LLM-native is our competitive advantage.
- Do not pretend platform coverage is comprehensive where it is heterogeneous. The
  brief is explicit: ~200-250 airports at credible B-lens depth, ~180-220 at C-lens
  per-passenger baseline, ~150-200 at credible D-lens depth. Differential coverage
  is honest; pretending otherwise is selling something we do not have.

== STACK DEFAULTS (do not deviate without founder reason) ==

- Backend: Python (FastAPI) + Pydantic
- Database: PostgreSQL (Supabase or Neon; I will pick)
- Document storage: Cloudflare R2
- Frontend (Phase 2 onwards): Next.js + Tailwind
- Map: Mapbox GL JS or MapLibre GL JS (Phase 2)
- Graph viz: D3 or Cytoscape (Phase 2)
- PDF generation (Phase 3): ReportLab or WeasyPrint
- Background jobs: Celery or RQ
- LLM orchestration: Anthropic Claude API via Python SDK
- Authentication (Phase 3): Auth0 or Clerk
- Hosting: Hetzner or DigitalOcean
- Python packaging: uv

== HOW WE WILL WORK ==

I am the founder. I have deep operational knowledge of airport infrastructure (via
Aprongrid, an airport ground power infrastructure venture, now terminated). I have
limited but real engineering literacy — I can read code, I can reason about
architecture, but I will not always notice subtle technical errors. You compensate
for that by being explicit about trade-offs and surfacing decisions rather than
hiding them in implementation choices.

We are building over 18-21 months to first revenue. Solo founder build. No VC.
Build with revenue. The pace is sustainable, not heroic. If you find yourself
proposing scope that requires 60-hour weeks indefinitely, descope.

Every session, before you begin substantive work, check the source registry at
/data/sources/ for current ingestion status and check recent commits to understand
state. If the brief has changed (revision history updated), re-read sections 1, 5,
7, 12, 13.

When you ship code, ship with tests. Not 100% coverage — pragmatic coverage of the
critical paths. The validation layers (XBRL vs PDF cross-validation, multi-source
transaction confirmation) are themselves tests in a sense.

When you encounter a verified data source that turns out to behave differently from
the brief, update /data/sources/{source}.json and tell me. Do not silently work
around it.

== NOW DO STEP 1 ==

Read PLATFORM_BRIEF_v4_LOCKED.md. Then summarise back per step 2 above. Then ask
for the dependencies per step 3. Then propose week 1 sequencing per step 4.

Do not write any code in this session until I have confirmed your week 1 plan.
```

---

## Notes on using this prompt

A few things worth knowing about how to deploy this.

**Run it in Claude Code, not in this chat interface.** Claude Code reads files, writes files, runs commands, and persists work between sessions in a way this chat doesn't. The brief and the prompt are intended for that environment.

**Have the brief in the working directory before you paste the prompt.** The very first action is "read PLATFORM_BRIEF_v4_LOCKED.md" — if it's not there, the session stalls. Put it at the repository root.

**Read Claude Code's summary back carefully.** The 5-8 bullet alignment check at step 2 is the most important friction point in the whole onboarding. If the summary reveals misunderstanding, fix it before any code is written. If it reveals genuine ambiguity in the brief that I missed, tell me — we update the brief, not the build.

**Expect the dependency list to be long.** Claude Code should ask for Anthropic API key, Companies House key, EDINET key, GitHub access, database hosting decision, object storage confirmation. If it asks for fewer than 4-5 things, something is off — push back and tell it to enumerate everything it needs.

**The week 1 sequencing proposal is also a check.** Compare it against Appendix C of the brief. Discrepancies suggest misreading, which we fix before coding.

**Don't let it skip the friction.** Solo builds with AI collaborators fail by drifting, not by stalling. The protocols in the prompt — flag tensions, locked decisions stay locked, schema versioning, provenance, LLM confidence scoring, assumption sets as first-class objects, API-first, idempotent ingestion, editorial separate, skills before writing — are not bureaucratic. They are the architectural commitments that distinguish a buildable platform from accumulating technical debt that swamps you in month 14.

**Resist asking it to "just start coding."** That impulse, while understandable, is how solo builds with LLM collaborators go sideways. The 30 minutes spent on alignment, dependency check, and sequencing proposal saves weeks of unwinding misaligned implementation later.

**Re-read the brief at every session start.** Or at minimum ask Claude Code to re-read sections 1, 5, 7, 12, 13 at session start. Context windows reset; commitments don't.

**The brief is the canonical reference.** When Claude Code's behaviour diverges from what you expected, the first thing to check is whether the brief is unambiguous on the point. If it isn't, the brief gets updated. If it is, Claude Code gets corrected. Don't argue case by case — argue from the brief.

---

## Suggested next 48-hour sequence

1. Register the four free accounts: Anthropic API, Companies House, EDINET, GitHub organisation
2. Decide on database hosting (Supabase vs Neon — both work; Supabase has slightly better defaults for solo founders)
3. Reserve the editorial publishing handle on Substack and confirm named-voice commitment
4. Block four hours next week for the first Claude Code session and the alignment friction it will require
5. Schedule the Macquarie warm-relationship outreach for Month 3, but draft the holding email now

Then start the build.
