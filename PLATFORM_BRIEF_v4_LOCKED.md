# Global Airport Infrastructure Intelligence Platform — Build Brief v4 (LOCKED)

> **Status.** LOCKED. This brief is the canonical reference for the build. v4 supersedes v1, v2, v3 entirely. Do not relitigate strategic decisions (§12) or propose rejected alternatives (§13). Operational uncertainties go to the founder, not silent choice.
>
> **Owner.** Alex (UK-based; sophisticated investor; warm Macquarie MIRA relationship; deep operational expertise in airport ground power infrastructure via Aprongrid — now terminated). Endenex (clean energy decommissioning intelligence) is a separate active venture and not in scope. The Aprongrid background is treated throughout this brief as a unique credibility asset for the editorial layer.
>
> **Purpose.** Master operational brief for any Claude Code session working on the platform. Read the whole document before architectural decisions. Where the brief explicitly anticipates a question, follow it; where it doesn't, raise it.
>
> **Build commitment.** Solo founder build with Claude Code. Target 18-21 months to revenue-generating platform, 30-42 months to exit. Target mid-case ARR £5-7m by month 36. Target mid-case exit £12-18m with £20-32m upside. Build with revenue. No VC funding.
>
> **Composite buildability confidence: P85-88** across 250-300 airport coverage at credible analytical depth across all three lenses.

---

## 1. Product identity

### One-line positioning

**The decision-support platform for capital allocation across global airport infrastructure.** Three analytical lenses — concession economics, commercial revenue intelligence, climate capital tracking — applied to 250-300 airports globally on one comprehensive structured data substrate. Built for institutional investors, strategic operators, and specialist consultancies making cross-asset, cross-jurisdictional airport infrastructure decisions.

### What it is

A continuously-updated analytical platform combining:

- **Comprehensive structured data layer** spanning financial filings, operational metrics, concession terms, ownership graphs, regulatory frameworks, and climate disclosures across ~250-300 airports globally
- **Three analytical lenses** that recombine this data to answer different decision questions — concession economics (B), commercial revenue intelligence (C), climate capital tracking (D)
- **Six user-facing analytical surfaces** — the Triptych airport view, Owner View, Deal Flow view, IC Paper Builder, Assumption Laboratory, Editorial canvas
- **LLM-native operational architecture** — continuous extraction pipelines for transactions, concession terms, sustainability disclosures, regulatory developments
- **Named-voice editorial layer** building over years from modest beginnings toward credible specialist authority

The product is decision-support for sophisticated institutional users, not a dashboard. The substance is analytical infrastructure — comparable cross-airport data with full provenance, supporting workflow-replacement outputs (IC paper builder, exportable analysis, assumption-set sharing) rather than dashboard consumption.

### What it explicitly is not

- Not a Bloomberg replacement. Live bond pricing, real-time trading feeds, and sell-side equity research are out of scope.
- Not a generic AI tool. Users have their own enterprise AI; the platform is the structured data layer their AI tooling runs on top of. API-accessible from launch.
- Not a transaction service. We don't broker deals.
- Not a sourcing platform. We don't list assets for sale.
- Not Inframation/IJ Global with airport focus. They are deal-tracking incumbents we partially compete with on the transaction layer, but our positioning is multi-lens analytical depth, not deal aggregation alone.
- Not a sustainability consultancy replacement. We provide structured climate capital data; bespoke advisory remains with ERM, Trucost, KPMG IMPACT etc.
- Not a route-economics platform. OAG, Cirium, Sabre own airline route analytics.
- Not aimed at the airline-side aviation industry. Customers are airport investors and operators, not carriers.

---

## 2. The six analytical surfaces

The platform's user interface organises around six analytical surfaces that recombine the underlying data layer to answer different decision questions. These are not separate modules in the traditional sense — they share the same data substrate and reorient based on user intent.

### Surface 1 — Capital Allocation Map (landing canvas)

**Purpose.** Geographic navigation primitive for the entire platform. Replaces a dashboard with a map of the global airport landscape.

**What user sees.** Interactive global map with every covered airport positioned geographically, sized by enterprise value, coloured by composite three-lens score. Filterable by ownership cluster, transaction status, regulatory cycle, climate disclosure quality. Right rail shows editorial week-in-review, firm-specific feed, regulatory calendar.

**Why this works.** Airport investors think geographically. Ownership thinks geographically. Capital flows are geographic. The interface matches the mental model rather than fighting it. The map is the navigation primitive; clicking an airport drills in, clicking an owner reorients the platform.

**Engineering.** Mapbox GL JS or MapLibre GL JS for the map layer; custom React components for markers and overlays. 4-6 weeks of focused work for production quality.

### Surface 2 — Airport Detail Triptych

**Purpose.** Force cross-lens analysis on every covered airport. Concession economics, commercial revenue, climate capital simultaneously presented.

**What user sees.** Three vertical panels with synthesis ribbon on top.

- **Synthesis ribbon (5 lines):** ownership chain summary, current EV and key multiples, concession horizon (or regulatory cycle position), commercial revenue trajectory descriptor, climate readiness score
- **Panel 1 — Concession Economics (B lens):** regulatory framework, traffic risk allocation, capex obligations, dividend constraints, refinancing schedule, covenant status, implied equity return at various assumption sets. Adjustable assumptions panel on right.
- **Panel 2 — Commercial Revenue Intelligence (C lens):** revenue decomposition (aero/non-aero baseline plus granular sub-category where disclosed), revenue per passenger by stream with peer comparison band, lease portfolio composition, real estate development pipeline. Killer view: "commercial upside scenario" — converging to upper quartile peer yields.
- **Panel 3 — Climate Capital Tracking (D lens):** decarbonisation capex commitments vs deployment, regulatory recovery mechanism analysis, SAF infrastructure status, climate disclosure quality scoring, credibility rating. Killer view: "transition cost waterfall" — capex hitting equity returns vs regulated charges over 10-25 years.
- **Below triptych:** horizontal strip showing airport's peer set on each dimension. Context-collapse fix.

**Engineering.** React with proper state management (Zustand). Cross-panel reactivity — change an assumption in B, climate panel recalculates. 6-8 weeks for polished triptych. The calculation engines underneath must be architected with assumption sets as first-class objects from day one.

### Surface 3 — Owner View

**Purpose.** Reorient platform to a specific owner's perspective. The genuine first-mover analytical surface — nobody currently aggregates this.

**What user sees.** Click "Macquarie" or "CK Infrastructure" or "Vinci Airports" — entire platform filters to that owner's airport portfolio. Map shows only their assets plus historical exits. Triptych views show owner-specific metrics (acquisition date, multiple paid, implied IRR to date, fund vintage holding-period patterns, estimated exit window). Cross-portfolio analytics for strategic operators (Vinci's 70+ airports with capex efficiency patterns, commercial yield convergence across acquisitions).

**Why this matters most for acquirer pitch.** When S&P Global / MSCI / climate-focused data platform evaluates acquisition, the Owner View is the screen that demonstrates unique value. The aggregation work is genuinely hard to replicate. Sell-side covers listed names. Inframation covers transactions. Consultancies do bespoke. Nobody puts CKI's complete global airport exposure with implied IRRs and exit windows on one screen.

**Engineering.** Graph visualisation for consortium structures (D3 or Cytoscape). 4-6 weeks for visualisation, ongoing maintenance for underlying data layer. The ownership graph data quality compounds over time — version 1 is rough, version 5 is genuinely valuable.

### Surface 4 — Deal Flow View

**Purpose.** Live transaction tracking and comparable analytics. LLM-native curation is the competitive position vs Inframation's legacy manual processes.

**What user sees.** Every airport transaction in last 24 months sized by deal value. Every airport currently for sale or rumoured to be. Every airport approaching exit window based on holding-period patterns. Filter by sponsor type, region, deal size, deal stage. Click any transaction for comparable analysis — multiples paid for similar assets, financing structures, who bid, who won, post-deal trajectory.

**LLM-native curation pipeline.** Continuous ingestion of news feeds (RSS, Google News, trade press), regulatory filings (SEC EDGAR 8-K, FCA NSM, EU competition consent decisions), stock exchange announcements, press releases. LLM classification identifies airport transactions. LLM extraction produces structured records. Cross-validation against multiple sources flags conflicts. High-confidence records auto-populate; low-confidence queue for review.

**Why this is a competitive advantage, not just a feature.** Inframation, IJ Global, Preqin curate transaction databases manually — analyst teams reading news and entering structured data with 2-7 day latency. LLM-native pipeline matches their data quality at materially lower operating cost with same-day latency. The acquirer thesis explicitly includes "platforms like Inframation want to acquire LLM-native infrastructure rather than retrofitting legacy systems."

**Engineering.** 3-4 weeks to build initial ingestion-classification-extraction-validation pipeline. Few hours per week ongoing maintenance and refinement. Operating cost roughly 5-10% of equivalent manual analyst team.

### Surface 5 — IC Paper Builder

**Purpose.** Workflow-replacement claim made concrete. The platform produces decision-ready outputs, not dashboards that need translating.

**What user sees.** User selects airport(s), selects analytical lens framing (acquisition diligence / divestment preparation / hold-or-sell / refinancing assessment / climate transition risk evaluation), platform generates 6-12 page draft IC paper as structured PDF. Full source attribution for every number. User edits and customises rather than building from scratch.

**Why this is a key differentiator.** Generic AI tooling can already draft first-version IC papers from analyst notes. What the platform adds: integration with verified structured data, audit-trail provenance that's IC-citable, IC-format templates, embedded charts pulled from platform analytics. The output is workflow-integrated, not generic.

**Engineering.** 8-12 weeks for credible v1. Template system, chart embedding, editable sections, PDF generation pipeline. Ongoing refinement as customers request format variations.

### Surface 6 — Assumption Laboratory

**Purpose.** Surface analytical disagreement structurally. Override platform assumptions, save personalised views, compare consensus vs house view vs stress case side by side.

**What user sees.** Every platform number has documented assumptions visible and editable. Override cost-of-debt assumption for Heathrow; entire platform recalculates. Save assumption sets. Compare "consensus view" vs "my house view" vs "recession scenario" across portfolio. Share assumption sets within firm — team's house view, senior partner's bearish overlay, analyst's first-principles rebuild.

**Why this matters for renewal.** This is the depth feature that's not visible in demos but drives retention. Once a firm builds team-shared assumption sets, switching cost is high. Platform becomes coordination layer for the team's analytical disagreements, not just an information source.

**Engineering.** Requires calculation engines architected with assumption sets as first-class objects. Adds 20-30% overhead to all calculation engine work. Must be designed in from day one, not retrofitted. The Laboratory UI ships in v1.5 once core calculation engines are stable.

### Surface 7 — Editorial Canvas (integrated, not separate)

**Purpose.** Editorial voice woven through platform rather than separate publication. Builds credibility gradually.

**What user sees.** Editorial pieces tagged with airports, owners, regulatory events, themes. When viewing Heathrow's climate panel and platform shows "partially credible" rating, link to editorial piece explaining why. When viewing Brazilian airport with aggressive implied IRR, editorial piece on LATAM concession bidder over-pricing one click away. Searchable editorial archive structured by topic, airport, owner, theme.

**Calibrated credibility expectations.** Editorial builds from zero. Piece 1: technically credible enough that someone forwarded doesn't dismiss, no authority claimed. Piece 30-50: first inbound contacts from sector. Piece 100+: occasional trade press references. Piece 200+ (year 3-4): meaningful niche authority. The editorial is the long-term moat — modest in year 1, meaningful by year 2, authoritative only by year 3-4. v1 demos lead with structured data, not editorial. Editorial is supplementary positioning, not the closer.

**Engineering.** Content management discipline rather than complex engineering. Tagging from day one. Editorial platform (Substack initially, platform-native eventually). Search index over editorial archive integrated into platform views.

---

## 3. The three analytical lenses

The platform's distinctive analytical posture is that every covered airport is viewed through three lenses simultaneously: concession economics, commercial revenue, climate capital. Each lens has its own data requirements, customer cohorts, and competitive landscape. Together they constitute the platform's unique positioning — no competitor combines all three.

### Lens B — Concession Economics

**What it covers.** Regulatory framework, traffic risk allocation, capex obligations, dividend extraction constraints, refinancing schedule, covenant status, regulatory return mechanics, concession horizon, change-of-control provisions.

**Why it matters.** Most direct mapping to investor decision criteria. When OTPP evaluates a Brazilian airport concession alongside an Italian one alongside a Vietnamese one, B lens normalises the comparison. Cross-jurisdictional concession comparison is the analytical surface that doesn't currently exist.

**Data sources.** World Bank PPI Database for emerging market concessions (201 airport projects, 30+ countries, full Stata dataset). LLM extraction from privatisation prospectuses for high-income airports. ESMA XBRL and SEC EDGAR XBRL for regulatory return mechanics. Individual operator regulatory accounts (Heathrow SP Regulatory Accounts CAA-mandated, similar in other jurisdictions).

**Customer pull.** Strongest from mainstream infrastructure equity funds (deal teams + asset management), specialist consultancies, sovereign wealth funds.

### Lens C — Commercial Revenue Intelligence

**What it covers.** Revenue decomposition (aeronautical vs non-aeronautical at minimum, granular sub-category where disclosed), revenue per passenger by stream, peer benchmarking, lease portfolio composition, real estate development pipeline, commercial yield trajectory.

**Critical analytical insight.** Per-passenger normalisation works across all airports with universally disclosed data: total revenue, aero/non-aero split, passenger numbers. Heathrow at £X non-aero per passenger, Schiphol at £Y, Beijing at £Z — comparable, useful, demonstrates C lens value at v1 with high-confidence universal data. Granular sub-category breakdown is v1.5 work where data quality varies.

**Why it matters.** Non-aeronautical revenue is increasingly the value driver for major airports. Heathrow's retail revenue per passenger is roughly 2x its peer set; Singapore Changi's Jewel commercial complex; Incheon's terminal commercial yield — these are real estate and retail businesses sitting on transport nodes. Investor analytics for this dimension is genuinely primitive in the market.

**Data sources.** ESMA XBRL and SEC EDGAR XBRL for total revenue and some sub-categories. Annual reports' narrative sections for aero/non-aero split (universally disclosed) and granular breakdown (variable quality). Eurostat avia_paoa for European passenger numbers. Per-airport monthly traffic releases. LLM extraction from annual reports for the granular detail.

**Customer pull.** Strong from strategic operators (commercial-revenue benchmarking against peers), mainstream infrastructure equity (asset management for held assets), REITs evaluating airport-adjacent property.

### Lens D — Climate Capital Tracking

**What it covers.** Decarbonisation capex commitments versus deployment, regulatory recovery mechanism analysis (how much capex recovers through regulated charges vs equity), SAF infrastructure pipeline, electrification status, climate disclosure quality (SBTi, CDP, TCFD, EU Taxonomy alignment), credibility scoring.

**Why it matters and why Aprongrid background is uniquely positioning.** Airport decarbonisation is in early years of 25-year deployment cycle. CORSIA mandates from 2027, EU ReFuelEU Aviation taking effect, UK Jet Zero implementation. The buyer set (climate-mandated infrastructure funds, sustainability-mandated mainstream funds, green bond investors) is forming with budgets being allocated right now. Your operational understanding of airport ground power and electrification economics is rare in this analytical space.

**Data sources.** SBTi targets database (verified — 39,274 companies, 43 airport entries, free XLSX). CDP scoring (partially free, partially paywalled). Airport sustainability reports via LLM extraction. ESMA XBRL and SEC EDGAR XBRL for regulatory recovery mechanism context. Engineering project documentation per airport. EU Taxonomy alignment disclosures.

**Customer pull.** Strongest from climate-mandated infrastructure funds. Mainstream ESG-mandated funds. Sovereign wealth with climate mandates. Green bond investors.

---

## 4. Coverage universe — 250-300 airports

### Coverage segments

**Tier 1: Listed airports with full structured financial data (~12-15 airports + CAAP's 50+ portfolio).**

- EU-listed via ESMA XBRL: AENA (Spain), Aéroports de Paris (France), Flughafen Wien (Austria), Toscana Aeroporti (Italy), Aeroporto Bologna (Italy), Copenhagen Airports (Denmark, 14 years filings), Malta International Airport
- ADR-listed via SEC EDGAR XBRL: OMA (158 IFRS concepts), GAP/Pacific Airport Group (215 concepts), ASUR/Southeast Airport Group, CAAP/Corporación América (352 concepts, covers 50+ airports across Argentina, Brazil, Uruguay, Ecuador, Italy, Armenia)
- TSE-listed via EDINET (free API key): Japanese airport operators including Narita and Kansai
- Other listed markets: ASX (Auckland Airport), HKEX (HK Airport Authority bonds), various BSE/NSE Indian operators

**Tier 2: Private but well-disclosed airports (~30-40 airports).**

- UK regulated: Heathrow group (HAHL, Heathrow Finance, Heathrow SP regulatory accounts), Gatwick group (Gatwick Funding, Gatwick Airport Finance plc, Ivy Holdco)
- European private: Schiphol Group (Contentful CDN workaround verified), Fraport (direct AEM PDF workaround verified), Munich Airport
- Strategic operator subsidiaries publicly disclosed: Vinci Airports portfolio (within Vinci SA consolidated), AENA international subsidiaries, AdP Group international subsidiaries
- Privatised concessions with public bond issuances: Manchester Airports Group, Birmingham, Edinburgh, Bristol, Newcastle

**Tier 3: Concession airports via World Bank PPI (~150-180 emerging market airports).**

- 201 airport projects in PPI database across Brazil (21), China (21), Mexico (21), Turkey (18), Colombia, India, Russia, Argentina, Egypt, Peru, Cambodia, Armenia, Philippines, Indonesia, etc.
- Rich descriptive fields (mean 1,564 characters per project) with sponsors, concession terms, financial structure
- LLM extraction of structured fields from narrative descriptions

**Tier 4: Strategic-operator-aggregated coverage (~50-70 airports).**

- Vinci Airports operates 70+ airports globally — single Vinci SA filing covers them in aggregate, with airport-specific disclosure in regulatory submissions
- AENA international: Mexico (12 airports via AENA Internacional), Brazil, Jamaica
- AdP Group: Mauritius, Jordan, Madagascar concessions
- Fraport: Lima, Antalya, Burgas, Varna, Greek regional airports portfolio
- Royal Schiphol Group: Eindhoven, Rotterdam (Netherlands), Brisbane (minority), JFK (minority)
- Changi Airports International: various Asian airport stakes

**Tier 5: Operational data only (~30-50 airports).**

- Airports without significant financial disclosure but with material operational data via Eurostat, ACI aggregates, individual monthly traffic releases
- Used for peer benchmarking and operational comparison even where deep financial data unavailable

### Excluded from coverage

- Heliports, military, general aviation, and non-commercial airports
- Airports with passenger numbers below ~1m annually (no institutional investor interest)
- Airports where no private capital participation exists (e.g., publicly-owned with no concession or bond presence)
- Airline-side aviation infrastructure (we cover the airport node, not airline route economics)

### Coverage philosophy

The platform aims for 250-300 airports at meaningful analytical depth across the three lenses. Coverage is heterogeneous by design — Tier 1 airports have full structured financial data plus operational data plus climate disclosures plus concession context, while Tier 5 airports have operational data plus peer benchmarking only. The platform reflects the reality of disclosure variance rather than pretending to comprehensiveness it doesn't have.

For B lens: ~200-250 airports at credible depth (Tier 1+2+3+4)
For C lens: ~180-220 airports at per-passenger benchmarking baseline; ~80-120 with granular sub-category data
For D lens: ~150-200 airports at credible climate disclosure depth; growing as climate reporting mandates expand

---

## 5. Data architecture — verified accessibility map

Every source listed as "verified" was programmatically tested via HTTP during the four dry-run phases (basic, workarounds, UI-driven, final).

### Tier 1 — Structured machine-readable feeds (no auth)

| Source | Coverage | Status |
|---|---|---|
| **ESMA filings.xbrl.org JSON:API** | EU-listed airports: AENA, AdP, Flughafen Wien, Toscana Aeroporti, Bologna, Copenhagen, Malta. Direct LEI lookup confirmed working. Pattern: `filter[entity.identifier]={LEI}` | ✅ Verified |
| **SEC EDGAR Company Facts API** (`data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`) | OMA (CIK 0001378239), ASUR (0001123452), GAP (0001347557), CAAP (0001717393, covers 50+ airports). Requires User-Agent header only, no key | ✅ Verified |
| **Eurostat avia_paoa SDMX 2.1 API** | All European airports, monthly passenger/movement/cargo data. 60,877 rows per month. Pattern: `avia_paoa/.....?startPeriod=YYYY-MM&endPeriod=YYYY-MM&format=TSV&compress=true` (5 dots = all dimensions wildcarded) | ✅ Verified |
| **OurAirports.com CSV** (`davidmegginson.github.io/ourairports-data/airports.csv`) | 85,346 airports globally, 3,309 commercial with scheduled service, 99% with IATA/ICAO/Wikipedia crosswalk | ✅ Verified — 12.6MB CSV |
| **OpenFlights routes** (`raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat`) | 67,663 routes between 3,321 airports | ✅ Verified — 2.4MB |
| **EUROCONTROL data snapshots** (`eurocontrol.int/archive_download/all/node/{id}`) | Periodic structured data releases including top 40 European airports peak days, structural metrics. 8+ snapshots accumulated | ✅ Verified — sample snapshot 58 returned 272KB ZIP with PDF + structured XLSX |
| **GLEIF LEI API** (`api.gleif.org/api/v1/lei-records`) | Global legal entity identifiers, free, no auth | ✅ Verified — Identity resolution works; parent relationships filed by ~30-40% of entities |
| **SBTi targets database** (`files.sciencebasedtargets.org/production/files/targets-excel.xlsx`) | 39,274 companies' science-based climate targets, 43 airport-related entries with full target detail | ✅ Verified — 5.4MB XLSX, 28 columns |
| **World Bank PPI Database** (Stata `.dta` via `datacatalogapi.worldbank.org/ddhxext/ResourceDownload?resource_unique_id=DR0051370`) | 16,051 projects total, 201 airport concessions in 30+ emerging market countries | ✅ Verified — 95MB Stata, rich descriptive fields |

### Tier 2 — Direct PDF/XLSX downloads (no auth, verified)

| Source | Verification | Notes |
|---|---|---|
| **Heathrow group documents** | ✅ HAHL AR 2024 (10.3MB), Heathrow SP Regulatory Accounts 2023 (1.1MB, CAA-mandated), Heathrow Funding AR 2022 (1MB) | Direct from heathrow.com `/content/dam/` paths |
| **Gatwick group documents** | ✅ Gatwick Airport Finance plc FS 2023 (2.8MB, 152 pages), plus 196 other PDFs across Ivy Holdco, Gatwick Funding, Gatwick Airport Limited entities | Direct from gatwickairport.com `/on/demandware.static/` paths |
| **Fraport via AEM workaround** | ✅ AR 2023 (13.8MB) | Pattern: `fraport.com/content/dam/.../Annual%20Report%20YYYY.pdf/_jcr_content/renditions/original.media_file.download_attachment.file/Annual%20Report%20YYYY` |
| **Schiphol via Contentful CDN workaround** | ✅ AR 2022 (8.8MB) | Schiphol.nl is Cloudflare-protected but `assets.ctfassets.net` CDN backing it is publicly accessible |
| **Heathrow bondholder regulatory accounts** | ✅ Multiple historical filings accessible | CAA-mandated, equivalent to regulator-mandated reports in other jurisdictions |

### Tier 3 — Authenticated APIs (free with registration)

| Source | Status | Notes |
|---|---|---|
| **Companies House UK API** | Verified accessible (401 without key) | Free key registration at developer.company-information.service.gov.uk. Public profile route also accessible without auth |
| **EDINET v2** (Japan) | Requires free Subscription-Key registration | Japanese TSE-listed airport entities |

### Tier 4 — LLM-native extraction pipelines (the operational architecture)

This is the platform's distinctive operational layer. Rather than manual analyst curation, LLM pipelines handle:

**Transaction database curation.** Continuous ingestion of news (RSS, trade press, press releases), regulatory filings (SEC EDGAR 8-K, FCA NSM, EU competition consent), stock exchange announcements. LLM classification identifies airport transactions, LLM extraction produces structured records, cross-validation flags conflicts. 3-4 weeks initial engineering, few hours per week ongoing maintenance.

**Concession terms extraction.** LLM pipeline reads airport privatisation prospectuses, concession agreements, regulator decision documents. Extracts traffic risk allocation, capex obligations, dividend constraints, change-of-control terms, extension rights. Reading 200 airport prospectuses with structured extraction prompt produces the database in days, not months.

**Sustainability disclosure extraction.** LLM ingests sustainability reports per airport, extracts Scope 1-3 emissions, decarbonisation capex commitments, SAF infrastructure plans, electrification status, Science-Based Targets validation status, TCFD compliance, EU Taxonomy alignment. Automatic schema normalisation across heterogeneous reporting styles.

**Commercial revenue decomposition.** LLM extraction from annual report narratives for aero/non-aero split (universally disclosed) and granular sub-category where available. Per-passenger normalisation calculated from extracted revenue ÷ passenger numbers from Eurostat or per-airport monthly releases.

**Cross-jurisdictional regulatory framework documentation.** LLM ingestion of regulator decision documents, regulatory frameworks, concession economic regulations. Structured normalised output covering allowed return mechanics, traffic risk allocation patterns, capex recovery mechanisms by jurisdiction.

**Ownership chain extraction.** LLM extraction of PSC chains, parent relationships, beneficial ownership from corporate registry filings (Companies House plus national registries where accessible).

**Validation layers.** Every LLM-extracted record has confidence scoring. High-confidence auto-populates. Low-confidence queues for founder review. Cross-validation against XBRL data where available; against multiple news sources for transactions; against regulator filings for ownership changes.

### Tier 5 — Workarounds for Cloudflare-protected and partial-access sources

| Source | Workaround | Status |
|---|---|---|
| **Schiphol Group** | Contentful CDN backing public site | ✅ Verified accessible |
| **Fraport** | AEM `_jcr_content/renditions/...` URL pattern | ✅ Verified |
| **Auckland Airport** | NZX disclosures + AnnualReports.com aggregator | ✅ Multiple paths working |
| **Sydney Airport** (private since 2022) | IFM Investors annual report references + ASX historical | ⚠️ Bounded data, parent-level analysis |
| **Zurich Airport** | Swiss SIX direct PDF (`report.flughafen-zuerich.ch/2024/ar/`) | ✅ Verified |
| **CAA UK statistics** | Accessible but redistribution-restricted ("no resold to third party") | ⚠️ Use for analytics; can't resell raw |

### Tier 6 — Operating costs and paid data subscriptions

- **Companies House API**: free with key
- **EDINET v2 API**: free with key
- **ACI World data subscriptions**: optional (~£15-30k/year), not required given Eurostat coverage for Europe and direct individual airport releases globally
- **OpenCorporates Pro**: optional (~£10-20k/year) for deeper international ownership chains; substitute with national registries + GLEIF + manual where needed
- **Cbonds**: optional for bond pricing data (~£5-15k/year)
- **Anthropic API**: paid, for LLM pipelines. Expected £500-2000/month at scale.

**Total external data subscription cost: £10-25k/year for v1.** Materially lower than original estimate of £30-50k because verified free sources (Eurostat, ESMA, SEC EDGAR, SBTi, World Bank PPI) cover most needs.

### Composite confidence by data layer

| Layer | Confidence |
|---|---|
| Reference data (OurAirports, OpenFlights, GLEIF) | P95+ |
| Financial structured data (ESMA + SEC EDGAR + direct PDF workarounds) | P92 |
| Operational data (Eurostat, EUROCONTROL, per-airport releases) | P90 |
| Climate/sustainability data (SBTi, CDP, sustainability reports) | P88 |
| Concession terms (World Bank PPI + LLM extraction from prospectuses) | P82-85 |
| Ownership graph (Companies House + GLEIF + national registries + LLM extraction) | P80 |
| Transaction database (LLM-native curation pipeline) | P85 |
| Commercial revenue at basic per-passenger normalisation | P85 |
| Commercial revenue at granular sub-category depth | P75 (heterogeneous coverage by airport) |

**Composite confidence on 250-300 airport platform across all three lenses: P85-88.**

---

## 6. User cohorts, pricing, TAM

### Cohorts ordered by year-one likelihood-to-pay

Calibrated for AI saturation reality — sophisticated users have enterprise AI; the platform sells structured data, methodology consistency, audit-trail provenance, unique analytical surfaces, and named-voice editorial (modest in year 1).

| Rank | Cohort | TAM | Pricing | 36-mo capture | Decision dynamics |
|---|---|---|---|---|---|
| **1** | **Specialist consultancies** (LeighFisher/Jacobs, ICF, Steer, ALG, Mott MacDonald, Arcadis, Ricondo, Landrum & Brown) | 10-15 firms | £80-180k | 5-9 firms, £500k-1.2m ARR | Heavy AI users already; platform extends their capability rather than replacing analyst time. Most likely acquirers. Cycle 3-6 months. |
| **2** | **Climate-mandated infrastructure funds** (Macquarie GIG, BlackRock Climate Infrastructure, Brookfield Climate, BNP Paribas Energy Transition, Mirova, AXA IM Alts, Foresight, Generation Investment Management) | 25-40 firms | £100-200k | 15-25 firms, £1.5-3m ARR | High urgency from LP ESG reporting mandates 2026-27. Buy for D lens primarily with B and C as context. |
| **3** | **Mainstream infrastructure equity — asset management teams** (Macquarie MIRA, GIP/BlackRock, IFM Investors, OTPP, OMERS, AustralianSuper, CDPQ, KKR Infrastructure, Stonepeak, Antin) | 30-45 firms | £120-250k | 12-20 firms, £1.5-4m ARR | Continuous-use buyer with monitoring budget. Macquarie warm relationship anchors. All three lenses. |
| **4** | **Strategic airport operators** (Vinci Airports, AENA, Fraport, AdP, Schiphol, Changi, Incheon, GMR, Adani, TAV, ASUR, OMA, GAP, CAAP, Vantage) | 12-18 firms | £100-200k | 6-10 firms, £600k-1.5m ARR | Competitive intelligence on peers. Politically delicate selling — they pay to monitor themselves. |
| **5** | **Credit funds and fixed-income desks** (M&G, Royal London, Insight Investment, BlackRock fixed income, Aviva Investors, AB CarVal) | 30-50 firms | £40-100k seat / £150-300k enterprise | 10-15 firms, £600k-1.5m ARR | CreditSights generalist + AI tooling is alternative. Wedge is specialist airport regulated-infra depth. |
| **6** | **Sovereign wealth + pension funds with direct airport exposure** (ADIA, GIC, NBIM, OTPP UK, CDPQ direct, NZ Super, Australian super funds, ATP Denmark, Mubadala, QIA) | 15-25 firms | £150-300k | 4-8 firms, £800k-2m ARR | Least price-sensitive, longest sales cycles (6-12 months), highest LTV. Quarterly editorial reports are their register. |
| **7** | **Investment banks — corporate finance and DCM** (BarCap, Citi, Lloyds, RBC, NatWest, SocGen UK infra desks) | 6-10 banks | £40-100k per team | 3-6 banks, £200k-500k ARR | AI has captured much of pitch deck generation. Lower willingness-to-pay than previously assumed. |
| **8** | **Mainstream infrastructure equity — deal teams** (same firms as cohort 3, different buyers) | 15-25 deal teams | £40-100k per team | 6-10 teams, £300k-800k ARR | Enter via firm-wide license that asset management bought. Episodic users tied to live processes. |

### Total realistic 36-month capture

55-93 customers, £6-13m ARR.
**Mid-case £8-10m ARR.**

### Exit valuation

- **Base case (specialist consultancy or sustainability data platform):** 1.5-2x revenue = £12-20M
- **Mid case (mainstream infrastructure data platform):** 2-3x revenue = £18-30M
- **Upside case (S&P Global, MSCI, Moody's Climate, ION/Inframation, Wood Mackenzie):** 3-4x revenue = £24-40M with LLM-native architecture story as material valuation premium

Strongest acquirer thesis: **LLM-native transaction database competes with Inframation's legacy manual processes.** Acquirers facing AI commoditisation of their data products want LLM-native infrastructure rather than retrofitting. This is a material competitive position.

VC funding remains rejected. Build with revenue.

---

## 7. Build sequence — phase-based

Five phases with explicit deliverables and gate criteria. Phase boundaries are commitments. Slippage signals reassessment, not pushing through harder.

### Phase 1 — Foundation (Months 1-6)

**Deliverable:** structured data layer for 200+ airports, calculation engines operational, LLM-native pipelines functional, no customer-facing UI yet.

**Engineering scope (parallel workstreams):**

- Repository, CI/CD, deployment infrastructure
- Database schema with methodology versioning, provenance tracking, calculation lineage from day one
- ESMA XBRL ingestion pipeline (filings.xbrl.org JSON:API)
- SEC EDGAR XBRL ingestion (data.sec.gov/api/xbrl/companyfacts/)
- EDINET ingestion (Japanese listed airports, free API key)
- Eurostat avia_paoa SDMX ingestion (European operational data)
- OurAirports + OpenFlights reference data ingestion
- World Bank PPI Database ingestion (Stata file processing)
- SBTi targets database ingestion
- GLEIF API integration
- Companies House API + public profile fallback
- Heathrow / Gatwick / Fraport / Schiphol direct PDF ingestion pipelines
- EUROCONTROL data snapshot ingestion
- **LLM-native transaction curation pipeline** (news + filings + press releases + classification + extraction + validation)
- **LLM-native concession terms extraction pipeline** (prospectus PDFs)
- **LLM-native sustainability disclosure extraction pipeline**
- **LLM-native commercial revenue decomposition pipeline**
- Calculation engines for cross-airport benchmarking, ownership graph traversal, per-passenger normalisation, regulatory return mechanics
- Methodology version tagging across all records
- Cross-validation logic (XBRL vs PDF extraction, multiple sources vs single)

**Editorial workstream (concurrent from Month 2):**

- Publishing platform setup (Substack initial)
- Editorial mission statement and topic backlog
- First piece ships Month 2, bi-weekly cadence thereafter
- Topic backlog maintained 4 weeks ahead minimum
- Calibrated expectations: piece 1 is foundation-building, not authority-asserting

**Gate criteria — Month 4 editorial check (do not skip):**

- Subscriber list ≥ 500
- At least 2 unsolicited inbound contacts from sector
- Editorial engagement (open rate) ≥ 30%

**If not met by Month 4: pause, reassess thesis, do not press on assuming it will pick up.** Editorial is the leading indicator. If sector isn't reading what you write before platform exists, platform won't change that.

**Gate criteria — Month 6 foundation check:**

- Structured data for ≥ 200 airports across all three lenses
- LLM pipelines operational with cross-validation working
- RoRE-equivalent calculations validated against published figures (Heathrow SP, AENA published returns, etc.) within tolerance
- Companies House integration populated for top 50 UK private airport entities
- Editorial archive of 6-8 published pieces

If foundation incomplete by Month 6: over-committed, descope before proceeding.

### Phase 2 — Demoable Wedge (Months 6-10)

**Deliverable:** working frontend for Triptych view, Owner View (top 10 owners), and Capital Allocation Map. Sufficient for cold-warm demos.

**Engineering scope:**

- Capital Allocation Map (Mapbox/MapLibre, 4-6 weeks)
- Airport Detail Triptych with cross-panel state management (6-8 weeks)
- Owner View for top 10 owners: CKI, Macquarie, Vinci Airports, AENA, Fraport, AdP, GIP/BlackRock, IFM, OTPP, Brookfield (4-6 weeks)
- Search, filter, basic personalisation
- Provenance click-through (any number → source documentation)
- Authentication scaffolding for early users

**Customer development:**

- First 6-10 warm-contact demos
- Priority sequence: specialist consultancies first, then climate-mandated funds (Macquarie GIG via MIRA warm), then mainstream infrastructure equity asset management teams
- Pilots not contracts
- Goal: product feedback + validation

**Editorial workstream:** continues bi-weekly. First quarterly special report shipped Month 9-10.

**Gate criteria — Month 10:**

- ≥ 3 active pilots
- ≥ 1 pilot in priority acquirer profile (specialist consultancy)
- Demo conversion ≥ 40% (warm intro → pilot)
- Editorial archive ≥ 15 pieces + 1 quarterly report

### Phase 3 — First Revenue (Months 10-15)

**Deliverable:** first paying customers, £400k-1m ARR, IC Paper Builder shipped.

**Engineering scope:**

- IC Paper Builder v1 (8-12 weeks): template system, chart embedding, editable sections, PDF generation with full source attribution
- Deal Flow view (LLM-native transaction database visualisation)
- Customer feature requests addressed inline (not deferred backlog)
- API documentation and access scaffolding

**Customer scope:**

- 4-7 paying customers
- £400k-1m ARR
- Customer base spans at least 2 cohorts (consultancies + climate-mandated or mainstream infra equity)
- First case studies / references usable for outbound

**Editorial workstream:** continues bi-weekly. Second quarterly special report Month 14-15. Archive ≥ 25 pieces.

**Gate criteria — Month 15:**

- ≥ 4 paying customers, ≥ £400k ARR
- Net revenue retention positive (no churn from converted pilots)
- Editorial subscriber list ≥ 1,500
- IC Paper Builder being actively used by at least 2 customers

### Phase 4 — Expansion (Months 15-21)

**Deliverable:** Assumption Laboratory shipped, 8-15 customers, £1-2.5m ARR, full coverage at depth.

**Engineering scope:**

- Assumption Laboratory with shared assumption sets (6-10 weeks)
- Cross-lens synthesis views (capex deliverability scorecards, mispricing screens)
- API release for enterprise customers
- Editorial archive search and tagging fully integrated
- Climate Capital Tracker enhancements (regulatory recovery analysis, SAF infrastructure detail)

**Customer scope:**

- 8-15 paying customers across 3-4 cohorts
- £1-2.5m ARR
- First multi-seat enterprise contracts
- First referral-driven customer (no founder-initiated outreach)

**Editorial workstream:** continues bi-weekly. Third and fourth quarterly reports. Archive ≥ 40 pieces. First public speaking invitations.

### Phase 5 — Scale + Exit Window (Months 21-42)

**Deliverable:** 25-45 customers, £5-7m ARR, acquisition conversations active.

**Engineering scope:**

- Feature work driven by customer pull, not roadmap
- White-label data feeds for consultancies
- Additional coverage decisions (smaller emerging market airports, regional consolidation)
- Editorial platform migration to platform-native if customer signal supports

**Customer scope:**

- 25-45 customers across all cohorts
- £5-7m ARR by Month 36
- At least 3 anchor customers at £150k+ ARR
- Customer base spans 4+ cohorts with no single cohort >40% of revenue

**Exit conversations:** open Month 24-30. Specialist consultancies most likely acquirers; data platforms as upside option. Sale closes Month 30-42 base case.

---

## 8. Engineering principles

These are non-negotiable architectural commitments. Future Claude Code sessions must operate within them.

### Provenance is non-negotiable

Every data record stored with: source_url, source_document_id, retrieval_timestamp, methodology_version, calculation_lineage (for derived values). Customers will challenge specific figures. We defend them with full audit trail.

### Schema versioning from day one

Every metric tagged with methodology version. Regulatory transitions (PR-equivalent changes in airport regulation, ICAO CORSIA from 2027, EU ReFuelEU Aviation phases) are anticipated rather than retrofitted. Cost of retrofitting is high. Discipline upfront matters.

### Calculation transparency

Every derived value traces to source data plus calculation steps. Click any number, see why it is what it is. This is the trust layer that distinguishes platform output from generic AI output.

### LLM-native operational architecture

Use LLM pipelines for: transaction curation, concession terms extraction, sustainability disclosure ingestion, commercial revenue decomposition, ownership chain extraction, regulatory framework normalisation. Don't manually curate what can be LLM-curated with appropriate validation.

Every LLM-extracted record carries confidence score. High-confidence auto-populates; low-confidence queues for founder review. Cross-validation against alternative sources where available.

### Assumption sets as first-class objects

Calculation engines architected with assumption sets as first-class objects from Phase 1, even though Assumption Laboratory UI ships in Phase 4. Retrofitting is painful. Designing in is manageable.

### API-first

API access available from launch (Phase 3), not deferred to v2. Users will pipe platform data into their own AI workflows. Design for that explicitly. The platform is the structured data utility their AI runs on top of.

### Ingestion idempotency

Re-running ingestion against the same source yields the same output. No state drift.

### Manual override with audit trail

When automated pipelines produce obviously-wrong figures, founder can override with editorial note. Audit trail preserved.

### Stack defaults

- **Backend:** Python (FastAPI) + Pydantic
- **Database:** PostgreSQL (TimescaleDB extension if time-series volumes warrant)
- **Document storage:** Cloudflare R2 (cost) or AWS S3
- **Frontend:** Next.js (React) + Tailwind, deferred to Phase 2
- **Map:** Mapbox GL JS or MapLibre GL JS
- **Graph viz:** D3 or Cytoscape for ownership graph
- **PDF generation:** ReportLab or WeasyPrint for IC Paper Builder
- **Background jobs:** Celery or RQ for ingestion pipelines
- **LLM orchestration:** Anthropic Claude API via Python SDK
- **Authentication:** Auth0 or Clerk for enterprise SSO when needed
- **Hosting:** Hetzner or DigitalOcean (£40-100/month initial)
- **Python packaging:** uv (modern default)

Don't deviate without explicit founder reason.

---

## 9. Editorial voice — calibrated expectations

### What it is

Named, public, opinionated voice on global airport infrastructure capital allocation. Technically grounded. Specific. Anchored in airport names, regulatory mechanics, financial structure. Not advocacy. Not consensus-respecting. Aprongrid background visible without being self-promotional.

### Cadence

- **Bi-weekly notes:** 1,500-2,000 words, single-topic, every other Tuesday
- **Reactive notes:** within 48 hours of major regulatory decisions or transaction announcements, 800-1,200 words
- **Quarterly special reports:** 6,000-10,000 words, themed
- **Year-in-review:** December annual deep dive

### Year-by-year credibility trajectory

- **Months 1-6 (pieces 1-12):** technically credible, no authority claimed, building topic backlog and writing skill
- **Months 6-12 (pieces 13-25):** first inbound contacts, occasional forward-along by sector readers
- **Months 12-24 (pieces 26-50):** consistency established, modest subscriber base (1,500-3,000), occasional trade press references
- **Months 24-36 (pieces 51-75):** recognised specialist voice in niche, meaningful inbound, first speaking invitations
- **Months 36+ (pieces 76+):** authoritative in niche, regularly referenced

**Acquisition multiple sensitivity to editorial maturity:** at month 36 exit, editorial adds maybe 10-15% to base multiple, not 30-50%. The structural moats (LLM-native architecture, comprehensive coverage, methodology consistency) carry the valuation. Editorial deepens but doesn't dominate.

### Topic discipline

The voice has authority on airport infrastructure capital allocation. It doesn't comment on:
- General macro / interest rates
- Politics beyond regulatory mandate
- Airlines (separate domain)
- Personal opinions on individuals (only on entity decisions)
- Platform marketing in editorial (editorial earns the right to mention platform sparingly)

### Quarterly report themes (suggested year 1 backlog)

- Q1 (Month 9-10): "What CAAP's portfolio tells us about LATAM airport concession dynamics"
- Q2 (Month 14-15): "The £400bn airport decarbonisation funding gap and who's filling it"
- Q3 (Month 20-21): "Why airport concession bidders are systematically overpaying for emerging market assets"
- Q4 (Month 26-27): "What Vinci Airports' 70+ portfolio teaches us about strategic operator scale"

Founder owns final selection.

---

## 10. Risk register

### Data layer risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **LLM extraction quality variance** | Medium | High | Cross-validation against XBRL where available; confidence scoring; low-confidence queue for founder review; ongoing pipeline refinement |
| **Concession terms heterogeneous quality by jurisdiction** | Certain | Medium | Coverage philosophy explicitly heterogeneous; framing as "best-in-market for what's disclosed" not omniscient |
| **Companies House / national registry access changes** | Low | Medium | Multiple paths (public profile + API); GLEIF as fallback identity resolver |
| **EU XBRL aggregator (filings.xbrl.org) outage or schema change** | Low | High | Cache aggressively; direct PDF fallback paths verified |
| **SEC EDGAR rate limiting** | Medium | Low | Polite User-Agent, throttle to within published limits |
| **Eurostat API quirks (extraction-too-big errors)** | Verified during dry run | Low | Chunk queries by month |
| **Cloudflare protection tightens on workaround paths** | Medium | Medium | Multiple paths per source (Schiphol Contentful, Fraport AEM); reassess if specific source breaks |

### Engineering risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Solo founder burnout** | High | Catastrophic | Part-time technical collaborator from Month 6; editorial cadence bi-weekly not weekly; gate-criteria discipline; realistic scope |
| **Assumption laboratory architectural debt** | Medium if not designed in | High | Calculation engines treat assumption sets as first-class from Phase 1 |
| **LLM pipeline maintenance burden** | Medium | Medium | Budget hours/week explicitly; design self-monitoring with confidence thresholds |
| **Cross-panel state management complexity in triptych** | Medium | Medium | Solid state management library; defer features that exceed solo founder complexity tolerance |
| **PDF generation pipeline (IC Paper Builder) underestimated** | Medium | High | Realistic 8-12 weeks budgeted; ship simpler v1 if needed |

### Commercial risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **International customer development slower than projected** | Medium | High | Realistic 6-12 month cycles built in; Macquarie warm anchors London; multiple cohort entry points |
| **AI tooling commoditisation outpaces platform differentiation** | Medium | Medium | LLM-native architecture not fighting AI but built around it; structural moats (data, methodology, audit-trail) less AI-vulnerable than user-facing features |
| **CreditSights aggressive defence of credit-monitor cohort** | Medium | Low (cohort is rank 5) | Specialist airport regulated-infra wedge; not direct competitor on whole platform |
| **Inframation/IJ Global respond to LLM-native challenge** | Medium | Medium | First-mover positioning matters; their legacy processes hard to retrofit quickly |
| **Acquirer market timing misaligned at month 36** | Medium | High | Multi-pathway exit options; long-tail independent operation always viable at £5-7m ARR |

### Editorial risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Editorial cadence collapses under build pressure** | High | High | Topic backlog 4 weeks ahead minimum; structural writing time blocked; bi-weekly committed (not weekly) |
| **Named-voice positioning doesn't compound as expected** | Medium | Medium | Calibrated expectations — editorial is supporting moat not primary differentiator; structural moats carry valuation |
| **Aprongrid background insufficient to establish credibility quickly** | Low | Medium | Background is genuine but unfamiliar to most readers; surface visibly in first few pieces |

### Founder-specific risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **18-21 months pre-revenue exceeds runway** | Founder-known | Catastrophic | Confirmed before commitment; bi-weekly cadence ensures public surface; reassess at Month 6 gate |
| **International travel cost and time burden** | Medium | Medium | Budget 8-15 trips/year; cluster meetings; remote-first sales motion where possible |
| **Macquarie warm relationship doesn't extend to global network** | Medium | Medium | Multiple cohort entry points; specialist consultancies as alternative anchor |

---

## 11. Success metrics

### Year 1 (Months 1-12)

- Editorial subscriber list: 1,000-2,500
- Engaged readership (weekly opens): 30-40%
- Platform pilot users: 3-7 institutions
- ARR: £400k-1m
- Macquarie design partner relationship active
- 25+ editorial pieces shipped
- 2 quarterly special reports
- LLM-native architecture validated through real usage

### Year 2 (Months 12-24)

- Subscriber list: 2,500-5,000
- Paying customers: 8-15
- ARR: £1.5-3M
- 50+ editorial pieces accumulated
- 4 quarterly reports shipped
- All six analytical surfaces live at credible depth
- First referral-driven customer

### Year 3 (Months 24-36) — exit window opens

- Subscribers: 5,000-10,000
- Paying customers: 25-40
- ARR: £4-6M
- 75+ editorial pieces
- Customer base spans 4+ cohorts
- API release with at least 5 enterprise data-feed customers
- Acquisition conversations active

### Year 3.5-4 (Months 36-42) — exit window

- ARR: £5-7M
- Customers: 35-45
- Acquisition closed at £12-30M (base to upside range)

---

## 12. Decisions locked — do not relitigate

1. **Airport infrastructure platform, not UK regulated infrastructure.** Aprongrid background uniquely positioning; market ceiling higher.
2. **Three lenses simultaneously (B+C+D), not single lens.** Underlying data layer 70-80% shared; broader cohort coverage; harder to copy.
3. **250-300 airport coverage at heterogeneous depth, not 40-60.** Cross-airport comparison surface requires breadth.
4. **LLM-native operational architecture, not manual analyst curation.** Competitive advantage vs Inframation/IJ Global legacy processes.
5. **API-first from Phase 3, not deferred to v2.** Users have their own AI; platform is the structured data layer.
6. **Editorial bi-weekly with calibrated credibility trajectory, not weekly with claimed authority.** Sustainable cadence + honest expectations.
7. **Build with revenue.** No VC funding. TAM doesn't support VC math.
8. **Per-passenger normalisation as universal C lens baseline.** Granular sub-category as incremental v1.5 depth where data permits.
9. **Macquarie as warm-relationship anchor, not paying-customer dependency.** Multiple cohort entry points reduce concentration risk.
10. **Specialist consultancies as cohort 1 (first paying customers and likely acquirers).** Climate-mandated funds cohort 2. Mainstream infra equity cohort 3.
11. **18-21 months pre-revenue acceptable.** Comprehensive build justifies longer runway.
12. **Schema versioning, provenance, calculation transparency non-negotiable from day one.**
13. **Methodology versioning anticipates regulatory transitions** (CORSIA 2027, ReFuelEU phases).
14. **AI-friendly architecture explicitly.** Designed for users running AI on top of platform data.
15. **Aprongrid and Endenex are separate ventures.** Not platform scope.
16. **UK regulated infrastructure platform plan (v3 LOCKED) superseded.**

---

## 13. Decisions rejected — do not propose

- UK regulated infrastructure platform (superseded)
- Single-lens platform (D-only, B-only, or C-only) — TAM insufficient
- 40-60 airport coverage (too thin for cross-comparison)
- Pre-revenue exit / VC funding (TAM mismatch)
- Manual analyst curation of transaction database (LLM-native is competitive advantage)
- Real-time bond pricing (Bloomberg owns)
- Airline-side aviation analytics (different market, OAG/Cirium territory)
- Pure dashboard product (no defensible moat)
- Free product (editorial free, platform paid; don't conflate)
- B2C / consumer-facing
- Region-specific platform (UK-only, EU-only, etc.)
- Weekly editorial cadence (unsustainable solo)
- AI-generated editorial (voice is moat; AI destroys it)
- Heavy paid data subscriptions (Eurostat + ESMA + SEC EDGAR + World Bank PPI cover most needs free)
- Browser automation as core dependency (Cloudflare workarounds verified for major blockers)
- Standalone climate consultancy positioning (we provide structured data; bespoke advisory stays with ERM, Trucost, etc.)

---

## 14. Open questions — for founder decision

These are flagged for explicit decision before substantial build, not assumed.

1. **Confirmation of Macquarie warm relationship temperature.** Specific person, last contact, willingness to be design partner with monthly product feedback from Month 3.
2. **Editorial cadence final commitment.** Bi-weekly Tuesday recommended. Confirm.
3. **Named voice confirmed (not pseudonymous).** Strong recommendation is named; confirm comfort.
4. **Editorial platform.** Substack v1, migrate platform-native later — confirm.
5. **First quarterly report topic.** Recommended: CAAP portfolio LATAM analysis as Q1 piece. Confirm or alternative.
6. **Pricing experiments with first 2-3 customer conversations.** Need real data points; founder runs and reports back.
7. **Technical collaborator hire timing.** Recommended Month 6; founder may prefer different timing.
8. **International travel commitment.** 8-15 trips/year expected; confirm willingness.
9. **Aprongrid background visibility in editorial.** Recommended visible in pieces 1-3 then organic thereafter; confirm tone.
10. **Anthropic API budget allocation.** LLM pipelines will burn meaningful tokens; budget £500-2000/month expected during scale; confirm.

---

## 15. Notes for Claude Code sessions

### How to use this brief

- Read sections 1, 5, 7, 12, 13 before any architectural decision
- Section 5 (data architecture) is operational reference for verified accessibility
- Section 7 is build sequence; defer cross-cutting work until its phase
- Sections 12 and 13 are constraints; don't propose alternatives
- Section 14 is open-questions list; flag rather than choose

### Specific gotchas

- **Schema versioning.** Every data record carries methodology version. No exceptions.
- **Calculation transparency.** Every derived value traceable to source data + calculation steps.
- **Provenance.** Every record has source_url, retrieved_at, source_document_id.
- **LLM confidence scoring.** Every LLM-extracted record carries confidence score. Auto-populate high-confidence; queue low-confidence.
- **Cross-validation.** Where multiple sources available (XBRL + PDF + news), validate against each other. Flag conflicts.
- **Don't confuse a data source with a coverage entity.** Eurostat is data source; airports are entities.
- **Don't conflate editorial product with platform product.** Editorial is free, named voice, lead-gen. Platform is paid, structured data, decision-support.
- **API-first.** Build internal APIs first; UI consumes APIs. Customer-facing API ships in Phase 3.
- **AI-friendly outputs.** CSV/Parquet/JSON exports from launch; users will pipe to their own AI.
- **Editorial separate from platform.** Different repositories, different deployments.
- **Anthropic API key.** Founder registers; env var, not code.
- **Companies House API key.** Founder registers; env var.
- **EDINET API key.** Founder registers; env var.

### Reference data registry

`/data/sources/` with one JSON file per source containing:
- Endpoint URLs verified
- Authentication requirements
- Refresh cadence
- Source format
- Last verified date
- Confidence rating
- Workaround paths if primary blocked

Update with every successful ingestion verification.

### Skills to consult

- `/mnt/skills/public/xlsx/SKILL.md` for SBTi targets database, ESMA XBRL packages
- `/mnt/skills/public/pdf-reading/SKILL.md` for annual reports, regulatory accounts, prospectuses
- `/mnt/skills/public/file-reading/SKILL.md` for general file ingestion routing

---

## Appendix A — Verified data source URLs

### Structured APIs (no auth)

- ESMA XBRL: `https://filings.xbrl.org/api/filings?filter[entity.identifier]={LEI}&include=entity`
- SEC EDGAR company facts: `https://data.sec.gov/api/xbrl/companyfacts/CIK{padded_cik}.json`
- SEC EDGAR submissions: `https://data.sec.gov/submissions/CIK{padded_cik}.json`
- Eurostat avia_paoa: `https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/avia_paoa/.....?startPeriod=YYYY-MM&endPeriod=YYYY-MM&format=TSV&compress=true`
- OurAirports: `https://davidmegginson.github.io/ourairports-data/airports.csv`
- OpenFlights routes: `https://raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat`
- GLEIF LEI lookup: `https://api.gleif.org/api/v1/lei-records?filter[entity.legalName]={name}`
- SBTi targets: `https://files.sciencebasedtargets.org/production/files/targets-excel.xlsx`
- World Bank PPI Stata: `https://datacatalogapi.worldbank.org/ddhxext/ResourceDownload?resource_unique_id=DR0051370`
- EUROCONTROL data snapshots: `https://www.eurocontrol.int/archive_download/all/node/{node_id}`

### Known LEIs for ESMA XBRL airports

- AENA: 959800R7QMXKF0NFMT29
- Aéroports de Paris: 969500PJMBSFHYC37989
- Flughafen Wien: 549300FQ2ILBH7DJ6I45
- Toscana Aeroporti: 8156005DBE6CA468DD09
- Aeroporto Bologna: 8156004CC118B7885065
- Copenhagen Airports (KØBENHAVNS LUFTHAVNE A/S): 549300Z01GJGM7D3HQ74
- Malta International Airport: 2138008EKXNMKZRXCT63

### Known CIKs for SEC EDGAR airports

- OMA (Central North Airport Group): 0001378239
- GAP (Pacific Airport Group): 0001347557
- ASUR (Southeast Airport Group): 0001123452
- CAAP (Corporación América Airports — covers 50+ airports): 0001717393

### Direct PDF workaround patterns

- Heathrow: `heathrow.com/content/dam/heathrow/web/common/documents/company/investor/reports-and-presentations/annual-accounts/{entity}/{filename}.pdf`
- Gatwick: `gatwickairport.com/on/demandware.static/-/Sites-Gatwick-Library/default/dw{hash}/images/Corporate-PDFs/{path}.pdf`
- Fraport: `fraport.com/content/dam/.../Annual%20Report%20{year}.pdf/_jcr_content/renditions/original.media_file.download_attachment.file/Annual%20Report%20{year}`
- Schiphol: `assets.ctfassets.net/biom0eqyyi6b/{contentful_id}/{hash}/Schiphol_Group_Annual_Report_{year}.pdf`

### Authenticated APIs (founder registers free)

- Companies House: `https://api.company-information.service.gov.uk/` (free key)
- Companies House public profile (no auth): `https://find-and-update.company-information.service.gov.uk/company/{number}`
- EDINET v2: `https://api.edinet-fsa.go.jp/api/v2/` (free Subscription-Key)
- Anthropic API: `https://api.anthropic.com/` (paid, for LLM pipelines)

---

## Appendix B — Confidence summary

**Composite buildability: P85-88** across 250-300 airport coverage at credible analytical depth across all three lenses.

**Component confidence:**
- Reference data: P95+
- Financial structured data: P92
- Operational data: P90
- Climate/sustainability data: P88
- Concession terms: P82-85
- Ownership graph: P80
- Transaction database (LLM-native): P85
- Commercial revenue per-passenger baseline: P85
- Commercial revenue granular depth: P75

**Bottleneck is not data accessibility.** It is solo founder capacity over 18-21 months, editorial cadence consistency, customer relationship cultivation across international geography, and LLM pipeline quality maintenance. The data layer is buildable.

---

## Appendix C — Claude Code handoff: first 30 days

### Pre-build founder actions (Day 0)

1. **Register Companies House API key** at developer.company-information.service.gov.uk (free, 10 min)
2. **Register EDINET v2 Subscription-Key** at api.edinet-fsa.go.jp (free)
3. **Register Anthropic API key** with appropriate workspace and budget
4. **Set up editorial publishing platform** (Substack). Reserve handle. Confirm named-voice commitment.
5. **Draft Macquarie holding email** for Month 3 outreach
6. **Decide editorial cadence finally** (recommended: bi-weekly Tuesday)
7. **Set up basic operational infrastructure** (GitHub organisation, password manager, accounting, business bank)
8. **Confirm stack defaults** per §8

### Week 1 — Repository and foundation scaffolding

1. Repository structure:
   ```
   /backend           - Python FastAPI services
   /frontend          - Next.js (deferred to Phase 2)
   /ingestion         - data ingestion pipelines, one module per source
   /llm_pipelines     - LLM-native extraction/curation pipelines
   /data/sources      - source registry (one JSON file per source)
   /data/schemas      - methodology-versioned schemas
   /tests             - unit + integration tests
   /docs              - internal documentation
   /editorial         - separate repository, separate deployment
   ```

2. CI/CD via GitHub Actions

3. Database schema with methodology-versioning architecture (explicit in §8)

4. Source registry initialised at `/data/sources/` with verified URLs from Appendix A

5. Generic ingestion harness supporting CKAN APIs, JSON:API, SDMX, direct PDF/XLSX/CSV downloads, Stata files

6. LLM pipeline scaffolding using Anthropic Claude API

### Week 2 — First ingestions (priority order)

1. **OurAirports + OpenFlights** — reference data foundation, used by every other ingestor
2. **ESMA XBRL via filings.xbrl.org** — verified working, test against AENA 2024 (LEI 959800R7QMXKF0NFMT29)
3. **SEC EDGAR XBRL Company Facts** — test against OMA (CIK 0001378239) and CAAP (CIK 0001717393)
4. **Companies House public profile** — test against Heathrow Airport Limited (company 01991017)

### Week 3 — Coverage expansion + first LLM pipeline

1. **Eurostat avia_paoa SDMX** — monthly query pattern verified
2. **EUROCONTROL data snapshots** — archive node enumeration and download
3. **World Bank PPI Stata** — load 95MB file, filter to airports, extract structured fields from description narratives via LLM pipeline (this is the first concrete LLM extraction pipeline — start here as it's bounded scope)
4. **SBTi targets database** — XLSX parser, filter to airport entries
5. **Direct PDF ingestors** for Heathrow, Gatwick, Fraport (AEM workaround), Schiphol (Contentful CDN workaround)

### Week 4 — Calculation engine v0 + editorial launch

1. **RoRE-equivalent calculation engine v0** validated against published Heathrow SP regulatory accounts within tolerance
2. **Per-passenger normalisation engine** for C lens baseline (revenue ÷ passengers for cross-airport comparison)
3. **First editorial piece ships.** Recommended topic: substantive analysis of latest CAAP results and what they reveal about LATAM concession dynamics. Sets the editorial register: data-grounded, opinionated, technical-but-readable. ~1,500 words.
4. **Editorial piece 2 scheduled** for week 6

### Architectural commitments — do not deviate without explicit founder decision

- Schema versioning from day one
- Provenance non-negotiable
- Calculation transparency
- LLM confidence scoring on every extraction
- Cross-validation against alternative sources
- Assumption sets as first-class objects in calculation engines
- API-first internal architecture
- Methodology-versioned storage

### Specific things Claude Code should NOT do without checking

- Add browser automation (Playwright) — workarounds verified for major blockers, defer
- Add real-time data feeds (bond prices, market data) — out of scope
- Build frontend in Phase 1 — backend only until Month 6
- Add features outside the six analytical surfaces in §2
- Make stack decisions contradicting §8
- Skip methodology-versioning architecture
- Use AI to generate editorial content
- Manually curate transaction database (use LLM-native pipeline)
- Pretend coverage is comprehensive where it's heterogeneous

### Reference for Claude Code at session start

1. Read sections 1, 5, 7, 12, 13 of this brief
2. Read this Appendix C
3. Check `/data/sources/` for current source registry status
4. Check recent commits to understand current state
5. Ask founder for current sprint priority if not obvious

---

## Revision history

- **v1** (initial UK regulated infrastructure draft) — superseded
- **v2** (post-dry-run UK regulated infrastructure with verified data accessibility) — superseded
- **v3 LOCKED** (UK regulated infrastructure with cohort sizing, phase-based sequencing, editorial leading indicator, Claude Code handoff) — superseded
- **v4 LOCKED** — pivot to global airport infrastructure intelligence platform. Three-lens architecture (B+C+D) on shared data substrate. Six analytical surfaces with Triptych as differentiating UI. LLM-native operational architecture as competitive advantage vs Inframation legacy. Calibrated editorial credibility trajectory. AI-saturation-aware value proposition. Per-passenger normalisation as universal C lens baseline. 18-21 month build to revenue. 30-42 month build to exit. £5-7m ARR mid-case, £12-32m exit range. P85-88 composite confidence verified through four dry-run phases.

---

*End of brief v4 (LOCKED). Strategic decisions in §12 and rejected alternatives in §13 are not to be relitigated. Operational uncertainties flag to founder. This document is the canonical reference for the build.*
