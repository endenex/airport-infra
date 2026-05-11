# Appendix D — Analytical Methodology Layers (Addendum to PLATFORM_BRIEF_v4_LOCKED)

> **Purpose of this document.** This appendix adds four cross-cutting analytical methodology layers to the platform specification. It does not modify §1-15 of the brief, the six analytical surfaces in §2, or any locked decisions in §12. These methodology layers integrate *into* the existing surfaces — they are analytical content that surfaces *through* the six interfaces, not additional UI surfaces.
>
> **Status.** Treat as locked addition to PLATFORM_BRIEF_v4_LOCKED. Do not relitigate the four layers' inclusion; they are committed.
>
> **What changes for the build.** Phase 1 engineering scope expands by approximately 8-12 weeks of additional work (methodology design plus expanded LLM ingestion pipelines). Build timeline extends from 18-21 months pre-revenue to 20-23 months. Exit valuation thesis strengthens — base case revises from £12-20M to £14-22M, upside from £24-40M to £28-48M.
>
> **What does not change.** The six analytical surfaces (§2 of brief). The three analytical lenses (§3). The 250-300 airport coverage universe (§4). The data architecture (§5). User cohorts and pricing (§6). Engineering principles (§8). Editorial approach (§9). The locked decisions (§12). The rejected alternatives (§13).

---

## Why these four layers were added

The original brief specified six analytical surfaces (Capital Allocation Map, Triptych, Owner View, Deal Flow, IC Paper Builder, Assumption Laboratory) plus Editorial. These surfaces answer the question "what's the structured analytical picture for this airport / owner / transaction." They are the foundation.

Sophisticated users, however, need answers to a different category of question — pattern-recognition questions that sit on top of the structured picture. Where is capital actually moving? What's the lifecycle position of this concession and therefore what analytical questions matter most for it now? Who else was at the table on past transactions and what does that tell us about who will bid next? What patterns have broken in the data that deserve human attention this week?

These are questions sophisticated users currently answer through tacit network knowledge, expensive bespoke work, or simply by going without good answers. They are not addressable by adding more data — they require analytical methodology applied across the data we are already accumulating.

The four layers each clear three bars: they answer a question sophisticated users currently can't easily answer; they compound from the existing data layer without requiring substantially new acquisition; they are defensible because the methodology and analytical synthesis require deep domain knowledge plus comprehensive coverage that competitors can't quickly replicate.

A fifth layer (Climate-Adjusted Equity Return) was considered and rejected. The analytical content is novel but the inputs carry compounded uncertainty (regulatory recovery percentages, physical climate cost estimates, transition scenario assumptions). Producing precise numbers that look more confident than they actually are is a credibility risk. The platform's climate analysis remains in the D lens (§3 of brief) without committing to single-number equity-return outputs.

---

## Layer α — Concession Lifecycle Position

**The question it answers.** "Where is this concession in its lifecycle, and therefore what analytical questions matter most for it right now?"

**Why it matters.** Every airport concession has a lifecycle position: early-stage (concession recently awarded, capex programme being deployed, financial structure still settling), mid-stage (steady-state operation, financial returns predictable), late-stage (concession approaching expiry, residual value analysis becoming critical, refinancing decisions tied to extension prospects). The analytical questions differ fundamentally at each stage. This framing currently exists only in tacit analyst knowledge.

**Methodology.** Every covered airport carries computed lifecycle position metadata. Inputs to the computation:

- Concession horizon remaining (years to expiry, where applicable)
- Capex programme completion percentage (deployed / total committed)
- Debt amortisation completion percentage
- Dividend extraction trajectory (when extraction started, what proportion of mid-life is complete)
- Time since concession award

These map to lifecycle stage categories with defined thresholds. Initial framework (founder owns final thresholds):

- **Early-stage:** <30% capex deployed AND <20% debt amortised AND concession horizon >70% remaining
- **Mid-stage:** 30-70% capex deployed OR steady-state operation evidenced (no major capex programme active, dividend extraction established)
- **Late-stage:** <30% concession horizon remaining OR >70% debt amortised OR formal extension negotiations under way

The framework itself is the analytical contribution. The thresholds are tunable via Assumption Laboratory once that ships in Phase 4.

**Where it surfaces in the platform.**

- **Triptych synthesis ribbon:** lifecycle stage shown prominently in the 5-line airport summary
- **Capital Allocation Map:** filterable by lifecycle stage (early-stage / mid-stage / late-stage filter chips in the right rail)
- **Owner View:** owner's portfolio distribution across lifecycle stages — concentration in late-stage signals exit urgency, concentration in early-stage signals capex burden
- **Query layer:** enables searches like "show me all early-stage LATAM concessions with capex deployment behind schedule" — answered in seconds because every airport carries lifecycle metadata

**Engineering scope.** 

- Methodology design and threshold definition: 2-3 weeks in Phase 1
- Calculation engine implementation (compute lifecycle position from existing inputs): 1-2 weeks in Phase 1
- Synthesis ribbon integration in Triptych: 1 week in Phase 2
- Map filter integration: 0.5 week in Phase 2
- Query layer: 1-2 weeks in Phase 2

**Total: roughly 6-9 weeks of engineering work, primarily Phase 1-2.**

**Confidence.** P88 — methodology is conceptually clean; inputs are well-defined and already in the data layer; coverage is comprehensive.

**Implementation notes for Claude Code session.**

- Lifecycle position is metadata, not a separate table. Add a `lifecycle_position` column (or equivalent computed property) to the airport entity, methodology-versioned per the existing schema versioning principle.
- Computation should be re-runnable. When a new financial period is ingested, lifecycle position recalculates automatically.
- Methodology version is critical here because thresholds will evolve. Store both the computed stage and the methodology version that produced it.
- Store the inputs to the computation (capex %, amortisation %, horizon remaining) alongside the output. Customers will challenge the classification; we defend it by showing what went into it.

---

## Layer β — Capital Flows

**The question it answers.** "Where is airport infrastructure capital actually moving — which funds are exiting, which sponsors are accumulating, which credit appetite is shifting?"

**Why it matters.** Every sophisticated airport investor has a mental model of where capital is moving in the sector. That model drives bidding decisions, exit timing, partnership selection. There's currently no structured surface for it — the model lives in tacit network knowledge and conference conversations. Building a structured surface is the most distinctive single analytical angle the platform can offer. It is the layer most likely to produce "wow" moments in demos.

**Methodology — five sub-views.**

**β.1 — Fund vintage maturity wall.**
Which infrastructure fund vintages hold airport assets, when those vintages mature, historical exit-pattern signatures by fund family. Macquarie Infrastructure Partners IV bought Asset X in 2018; MIP IV is a 10-12 year vintage; therefore exit likely 2026-2028. Multiplied across every fund vintage holding airport assets, this produces a structured supply-side view of likely airport transactions in the next 12-36 months.

Data inputs: fund vintage information (extracted from fund disclosures via LLM pipeline), historical holding period patterns by fund family (from accumulated transaction database), current ownership graph (already in the platform).

**β.2 — LP commitment shifts.**
Annual allocation reports from public pension funds (CalPERS, OTPP, NBIM, CDPQ, AustralianSuper, etc.) and sovereign wealth fund annual reports show infrastructure allocation moves over time. LLM-extracted and tracked. Output: view of where new airport-investing capital is forming and where existing commitments are growing or shrinking.

Data inputs: annual reports of major LPs (LLM ingestion pipeline, runs annually), LP-to-fund mapping (built up from manager disclosures).

**β.3 — Strategic operator accumulation patterns.**
Historical pattern recognition across Vinci's 70+ portfolio acquisitions over 15 years, AENA international expansion, Fraport portfolio building, AdP Group expansion, Changi international stakes. Output: probabilistic view of where each strategic operator is likely to bid next based on their historical pattern (geographic preferences, deal sizes, stake structures, consortium composition).

Data inputs: accumulated transaction database (already being built per brief §5 LLM-native transaction curation), operator-by-operator historical pattern analysis.

**β.4 — Co-investment network graph.**
Who has consortium-partnered with whom on past deals. GIP and Macquarie on certain assets, IFM and AustralianSuper on others, Brookfield with various sovereign wealth co-investors. The consortium network has real predictive power — when GIP needs a partner for a new bid, historical partners are more likely than random firms.

Data inputs: transaction database with consortium composition fields, graph analytics over historical partnerships.

**β.5 — Credit appetite signals.**
When the same airport refinances and bond pricing tightens or widens, when covenant terms loosen or tighten, when credit fund participants change. Aggregating these signals across the universe gives a sector credit-cycle indicator.

Data inputs: bond issuance disclosures (LLM-extracted from prospectuses), refinancing data from regulatory filings, credit fund participation tracking.

**Where it surfaces in the platform.**

- **Owner View:** Capital Flows is a viewing mode within Owner View. Switch from default "asset detail" view to "capital flows" view and see fund vintage maturity wall for that owner, the accumulation pattern, the consortium network, the credit appetite signals affecting their portfolio.
- **Deal Flow View:** Capital Flows is also a viewing mode within Deal Flow. From transaction-by-transaction view, switch to capital-flows aggregation showing which fund vintages are driving current transaction activity, which LPs are funding current acquisitions, which consortium networks are forming or breaking.

**Critical integration discipline:** these are viewing modes, not new UI surfaces. Same data, different analytical framing. Resist the temptation to create separate "Capital Flows" navigation.

**Engineering scope.**

- LLM ingestion pipeline for LP commitment reports (CalPERS, OTPP, NBIM, CDPQ, etc.): 2-3 weeks in Phase 1
- Fund vintage extraction methodology and pipeline: 1-2 weeks in Phase 1
- Strategic operator accumulation pattern analysis: 2-3 weeks (methodology design + implementation), Phase 1-2
- Consortium network graph analytics: 1-2 weeks in Phase 2
- Credit appetite signal aggregation: 1-2 weeks in Phase 2
- Surfacing into Owner View and Deal Flow View: 2-3 weeks in Phase 3

**Total: roughly 10-15 weeks of engineering work, spanning Phases 1-3.**

**Confidence.** P82 — fund vintage and consortium network synthesis are straightforward from accumulated data. LP commitment extraction requires sustained LLM pipeline maintenance. Pattern recognition for strategic operator next-moves is probabilistic and improves over time as the data accumulates. Capital Flows is the layer most likely to deliver the "wow" moment in demos, but year-1 outputs will be partial; the layer compounds substantially across years 2-3.

**Implementation notes for Claude Code session.**

- LP commitment reports run annually — the ingestion pipeline doesn't need to run continuously. Annual cadence aligned to LP reporting cycles is fine.
- Strategic operator pattern analysis is probabilistic output. Frame in UI as "historical pattern + likely-direction" not "prediction." Surface confidence levels alongside outputs. Let Assumption Laboratory users override.
- Consortium network graph should use the same ownership graph infrastructure (D3 or Cytoscape per stack defaults). Don't build separate graph viz.
- Credit appetite signals require accumulated bond data over time. Year 1 output will be sparse; methodology should be designed to compound.

---

## Layer γ — Counterfactual

**The question it answers.** "For every transaction that closed, who else was at the table and at what price? For every process that was abandoned, who participated and why did it fall apart?"

**Why it matters.** Every closed airport transaction has 2-5 transactions that didn't close — losing bids, pulled deals, abandoned processes, postponed refinancings. This near-miss information contains enormous analytical value: who bid what, why they walked, what terms they wouldn't accept, what the rival bid coverage looked like. It is currently locked in tacit network knowledge — analyst memory, deal-team recollection, conference panel disclosures. 

The LLM-native ingestion architecture makes systematic capture of this scattered information economically viable in a way manual curation never could. This is one of the layers most uniquely enabled by the platform's LLM-native operational architecture (per brief §5 Tier 4).

**Methodology.** Expanded LLM ingestion to capture not just closed transactions but also:

- Bid submission disclosures (some jurisdictions require these to be public)
- Regulatory consent decision documents (which describe rival bidders and process timeline)
- Press leaks during processes (rumoured bidders, abandoned attempts)
- Retrospective interviews and post-mortem coverage in trade press
- Court documents from disputed processes
- Industry conference panel discussions and analyst transcripts mentioning specific processes
- Sponsor public statements after losing or withdrawing

Schema design handles:
- Transaction state: closed / abandoned / pulled / bid-lost / postponed
- Rival bidder status: identified / suspected / unknown
- Reason-for-failure: disclosed / inferred / unknown
- Price information: confirmed / rumoured / range

**Where it surfaces in the platform.**

- **Deal Flow View:** Counterfactual is a data category extension within Deal Flow. When you click any closed transaction, you see not just the close but the rival bid pattern and abandoned alternatives in that period.
- **New query patterns enabled:**
  - "Show me historical bid coverage for emerging-market concession processes" → returns realised distribution of bidders per process
  - "Show me all abandoned UK airport refinancings in the last 5 years" → returns sponsor-failure pattern
  - "Show me historical close rates by process type" → returns advisor-pitch ammunition
  - "Show me losing bidders on Vinci's last 10 acquisitions" → returns competitive pattern intelligence

**How the layer compounds.** Year 1 of counterfactual data is sparse — much of the historical information has to be reconstructed retrospectively from various sources. Year 3 of accumulated data is genuinely powerful because the platform captures near-miss information continuously and the historical archive deepens.

**Engineering scope.**

- LLM ingestion sources expansion (bid disclosures, regulatory consent docs, retrospective coverage): 2-3 weeks in Phase 1
- Schema design for counterfactual transactions (state, rival bidder status, reason, price): 1 week in Phase 1
- Retrospective backfill of historical near-miss data: ongoing through Phases 1-3, gradually deepening
- Surfacing into Deal Flow View: 1-2 weeks in Phase 3
- Query layer enabling counterfactual-specific queries: 1-2 weeks in Phase 3

**Total: roughly 5-8 weeks of focused engineering, plus ongoing backfill work.**

**Confidence.** P78 — the data sources exist and are LLM-ingestible but coverage will be inherently incomplete. Some near-miss information genuinely isn't public. Frame the layer as "best-in-market structured visibility into deal counterfactuals" rather than "comprehensive."

**Implementation notes for Claude Code session.**

- Counterfactual records share the transaction schema. They're not a separate table; they're transactions with state = abandoned/pulled/bid-lost.
- LLM extraction confidence scoring is especially important here. A rumoured bidder from a press leak is lower confidence than a regulatory consent doc explicitly naming bidders. Surface confidence in UI.
- Be careful with attribution. If trade press reported that "GIP and KKR were among rumoured bidders" but neither confirmed, the platform records "GIP (rumoured)" and "KKR (rumoured)" — never assert they bid without disclosure backing.
- The retrospective backfill is ongoing curation work. Budget founder hours per week for reviewing low-confidence flagged extractions.

---

## Layer δ — Anomaly Detection

**The question it answers.** "What should I be paying attention to that I'm not? Across 250-300 airports, what patterns have broken or what disclosures have changed that deserve a human look?"

**Why it matters.** Continuous monitoring across the full coverage universe surfaces patterns no individual analyst would catch through normal portfolio monitoring. Compute can do what human attention cannot — sustained vigilance across hundreds of airports simultaneously. The analyst gets a curated list of "things worth your attention this week" rather than having to maintain attention across 250-300 entities.

**Methodology categories.**

**δ.1 — Disclosure anomalies.**
Year-over-year changes in how an airport categorises revenue, capex, or sustainability metrics. Sudden reduction in disclosure granularity (potentially hiding underperformance). Peer airports adopting a metric this one stops disclosing. Material auditor or accounting policy changes.

**δ.2 — Operational pattern breaks.**
Monthly traffic deviating from rolling 24-month trend by >2 standard deviations, sustained for >2 months. Cargo volumes diverging from passenger trends in unexpected ways. Aircraft movement composition shifts (long-haul vs short-haul). Slot utilisation pattern changes at slot-constrained airports.

**δ.3 — Ownership signal patterns.**
Fund holding an asset past typical vintage holding period without stated reason. Consortium structure changes mid-hold without disclosure. Sponsor reporting cadence becoming less frequent or less detailed. Senior management changes at the operating entity.

**δ.4 — Cross-airport pattern breaks.**
Airport's commercial revenue per passenger sustained deviation from peer set. Capex execution pace materially different from peer-average. Climate disclosure quality diverging from peer set. Regulatory return achievement diverging from peer set within the same regulatory framework.

**δ.5 — Financial structural anomalies.**
Covenant headroom approaching threshold levels. Refinancing windows opening sooner than expected. Cash flow trajectories diverging from initial concession plan. Dividend extraction pattern changes.

**Where it surfaces in the platform.**

- **Capital Allocation Map right rail:** "This week's flags" showing the 5-15 airports with active anomalies, each flag explaining why it surfaced
- **Triptych airport view:** airport-specific flags shown inline (small icon indicators on relevant data points with hover-explanation)
- **Owner View:** aggregated anomaly flags across an owner's portfolio
- **Email digest (optional, Phase 3+):** weekly summary of flagged anomalies to subscribed users

**Critical framing constraint.** Anomalies are surfaced as flags for human review, never as predictions or alerts demanding action. The register is "these 7 airports show patterns worth your attention this week, here's why" not "we predict X will face a covenant breach in Q3." One wrong prediction destroys credibility built over years; a flag that turns out to be benign costs nothing because the framing was always "worth a look" not "definitive signal."

This framing discipline is non-negotiable. The Claude Code session should never implement UI text or notification copy that suggests prediction. Always "pattern detected" / "deviation observed" / "worth attention" — never "expect" / "predict" / "will."

**Engineering scope.**

- Methodology design per anomaly category (5 categories, each requiring sector-specific definition of what counts as anomalous): 3-4 weeks across Phases 1-2
- Statistical implementation (rolling baselines, deviation calculations, threshold management): 3-4 weeks in Phase 2
- Notification surface integration (map right rail, Triptych inline flags, Owner View aggregation): 2-3 weeks in Phase 2-3
- Tuning and false-positive management: ongoing throughout Phase 3-5

**Total: roughly 8-11 weeks of focused engineering, plus ongoing tuning.**

**Confidence.** P75 — methodology is sound but false-positive rates will require sustained tuning. The framing-as-flags-not-predictions discipline is the credibility protection. Year 1 should run the layer in "founder-only" mode (flags surface to founder for review and tuning, not to customers) before exposing to user-facing surfaces.

**Implementation notes for Claude Code session.**

- Run in shadow mode initially. Year 1 Phase 1-2 the layer generates flags that surface only to founder review. Phase 3 onwards the layer surfaces flags to customers, but only flag types with proven low false-positive rates are exposed.
- Each flag carries: airport, anomaly category, methodology version, statistical evidence, similar past flags and their outcomes, link to underlying data.
- Tuning is per-anomaly-type. Disclosure anomalies need different thresholds than operational pattern breaks. Don't build a single global anomaly threshold.
- The "similar past flags and their outcomes" feedback loop is critical. When a flag resolves (covenant breach materialised vs benign), record the outcome and use it to tune thresholds.
- Never frame flags as predictions in UI copy. The Claude Code session should enforce this through review.

---

## Summary integration table — where the four layers surface

| Methodology layer | Primary surfacing | Secondary surfacing |
|---|---|---|
| **α Concession Lifecycle Position** | Triptych synthesis ribbon | Map filter, Owner View portfolio distribution, query layer |
| **β Capital Flows** | Owner View viewing mode | Deal Flow View viewing mode |
| **γ Counterfactual** | Deal Flow View data category | Query layer enabling counterfactual-specific searches |
| **δ Anomaly Detection** | Map right rail "this week's flags" | Triptych inline flags, Owner View aggregation, optional email digest |

No new UI surfaces. Four layers integrate into the six analytical surfaces specified in brief §2.

---

## Aggregate impact on build

**Engineering scope added:** 29-43 weeks of additional engineering work distributed across Phases 1-3, with ongoing tuning and curation thereafter.

**Build timeline:** 18-21 months pre-revenue revises to **20-23 months pre-revenue**. Within tolerance — these aren't features, they're distinctive analytical content that justifies the platform's positioning beyond "structured airport data."

**Composite buildability confidence:** stays at P85-88. The additions are methodology and analytical framing, not new data accessibility challenges. The data layer is already verified per brief §5.

**Per-layer confidence:**
- α Concession Lifecycle Position: P88
- β Capital Flows: P82
- γ Counterfactual: P78
- δ Anomaly Detection: P75 (with strict framing discipline)

**Exit valuation:** strengthened.
- Base case: £14-22M (from £12-20M)
- Mid case: £20-35M (from £18-30M)
- Upside case: £28-48M (from £24-40M)

The methodology layers create defensible analytical IP that acquirers cannot replicate from data alone. Capital Flows in particular is the kind of pattern-recognition product established data platforms repeatedly try and fail to build because they lack the deep sector knowledge to define the methodology credibly.

---

## What this addendum does NOT change

- The six analytical surfaces in brief §2 (Capital Allocation Map, Triptych, Owner View, Deal Flow, IC Paper Builder, Assumption Laboratory)
- The three analytical lenses in brief §3 (B Concession Economics, C Commercial Revenue, D Climate Capital)
- The coverage universe of 250-300 airports in brief §4
- The data architecture and verified accessibility map in brief §5
- The customer cohorts, pricing, and TAM in brief §6
- The engineering principles in brief §8 (provenance, schema versioning, calculation transparency, LLM-native, assumption sets as first-class, API-first, idempotency)
- The editorial approach in brief §9
- The 16 locked decisions in brief §12
- The rejected alternatives in brief §13

---

## Locked decisions added by this addendum

17. **Concession Lifecycle Position (Layer α) as core metadata.** Every covered airport carries computed lifecycle position. Methodology versioned. Tunable via Assumption Laboratory.

18. **Capital Flows Layer (Layer β) as viewing mode within Owner View and Deal Flow View, not separate UI surface.** Five sub-views: fund vintage maturity, LP commitment shifts, strategic operator accumulation, consortium network, credit appetite.

19. **Counterfactual Layer (Layer γ) as data category extension within Deal Flow View.** Captures abandoned processes, losing bids, postponed deals alongside closed transactions. Schema includes transaction state, rival bidder status, reason-for-failure, price information with confidence levels.

20. **Anomaly Detection Layer (Layer δ) framed as flags-for-human-review, never as predictions.** Run in shadow mode (founder-only) in early phases. Customer-facing surfacing only for flag types with proven low false-positive rates.

21. **Climate-Adjusted Equity Return view explicitly rejected.** Compounded uncertainty in inputs (regulatory recovery percentages, physical climate cost estimates, transition scenario assumptions) creates credibility risk. Climate analysis stays in D lens without single-number equity-return outputs.

---

*End of Appendix D. Treat as locked addition to PLATFORM_BRIEF_v4_LOCKED. Strategic decisions in this addendum are not to be relitigated. Implementation notes for Claude Code session under each layer.*
