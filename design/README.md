# Handoff: Federal Regulation Query — Interface Redesign

## Overview

A **cosmetic redesign** of *Government Regulation Query* (live at `regs.bradhinkel.com`) — a
retrieval-augmented search engine over the U.S. Code of Federal Regulations. Users ask a
plain-English question and receive three grounded answers: a plain-English explanation, a formal
legal-language synthesis with verbatim statute quotes, and a list of precise CFR citations.

This redesign keeps the existing information architecture and feature set. It changes only the
**visual system and presentation** — the design north star is **trust and verifiability**: making
provenance, freshness, and grounding feel first-class rather than like muted afterthoughts. The
direction is editorial / "Official Record": authoritative, document-like, calm.

The backend, retrieval pipeline, data model, and routing are unchanged and out of scope.

---

## About the Design Files

The files in this bundle are **design references created in HTML/CSS + React (via in-browser Babel)**.
They are a high-fidelity prototype demonstrating the intended look, layout, and interactions — **not
production code to ship directly.**

The task is to **recreate this design in the target codebase's existing environment.** Per the
product overview, that stack is **Next.js 14 (App Router) + TypeScript + Tailwind CSS**, with
components in `frontend/app/components/` and theme tokens in `frontend/app/globals.css`. Re-implement
these designs as real React/TypeScript components using Tailwind (or the project's existing CSS-variable
theming), wiring them to the existing API/state. Treat the HTML/CSS here as the **source of truth for
visual values** (colors, type, spacing, layout, interaction), not as files to copy.

This prototype uses **mock data** (`data.js`) and a fake pipeline timer to demo states. In production,
those come from the real backend.

---

## Fidelity

**High-fidelity (hifi).** Final colors, typography, spacing, and interactions are specified. Recreate
the UI pixel-accurately using the codebase's libraries and patterns. Exact hex values, font families,
sizes, and radii are listed in **Design Tokens** below and defined as CSS variables in `styles.css`.

---

## Visual System (the redesign at a glance)

- **Theme:** Dark by default (formal, matches the existing product). A polished **light** ("warm paper")
  theme is fully specified and toggleable — implement both via a `data-theme` attribute swapping the
  CSS-variable set. Default = dark.
- **Typography (3 typefaces):**
  - **Public Sans** — UI: labels, meta, buttons, nav, chips. (Chosen deliberately: it's the official
    US Web Design System typeface.)
  - **Spectral** (serif) — display/headlines, the question headline, **and the answer prose body**
    (both Plain-English and Legal registers). Long-form legal text reads far better in a serif than
    the original monospace.
  - **IBM Plex Mono** — CFR citation references (`§` numbers), latency/strategy meta, step numbers.
- **Accent:** Federal blue `#5183ff` (dark) / `#2d5fd6` (light). Used sparingly — links, primary
  button, headings-of-sections, citation numbers.
- **Reserved "statute gold"** `#cba85f` — used *only* for verbatim quote blocks, to signal "this is
  the actual law" vs. synthesized prose. Do not use gold elsewhere.
- **Verified green** `#56b78f` — grounding/freshness trust signals and the "high confidence" tier.
- Single centered column, **max-width 1080px** (wider than the original 768px to accommodate the
  citations rail).

---

## Screens / Views

There are **five screen states**, all within the single main route (plus an About modal). In the
prototype they're switched via React state / the Tweaks "Preview screen" selector; in production they
map to the real query lifecycle.

### 1. Home / empty (first-run) state

- **Purpose:** Entry point. User composes a question, optionally filters by CFR title and picks a
  strategy, then searches. First-time users learn what the tool does.
- **Layout:** Vertical stack inside the centered 1080px column, 28px side padding.
  1. **Masthead** (shared across all screens) — see below.
  2. **Eyebrow** — uppercase 11px Public Sans, letter-spacing 0.16em, muted, with a small
     verified-green shield-check icon: "RETRIEVAL-AUGMENTED · GROUNDED IN THE ACTUAL CFR TEXT".
     16px below masthead.
  3. **Composer card** — see Components.
  4. **Composer disclaimer note** — 12px muted, shield icon, 13px below composer:
     *"Informational only — not legal advice. Every answer is grounded in the current eCFR; verify
     against the official text at ecfr.gov before relying on it."*
  5. **Examples** — label "TRY ONE OF THESE" (11px/700/0.12em uppercase muted), then a flex-wrap row
     of 4 chips. 22px above.
  6. **How-it-works** — a 3-column grid (1px gaps, hairline borders, panel bg) of steps. 44px above.
  7. **Coverage strip** — label "COVERAGE — 8 MAJOR TITLES", then 8 title tags. 40px above.

#### Components — Home

- **Composer card**
  - Container: `linear-gradient(180deg, --surface, --panel)`, 1px `--border`, radius 14px, card shadow.
  - Top region (22px 24px 4px padding): a `<textarea>` — **Spectral 19px**, line-height 1.5,
    min-height 84px, transparent, no resize. Placeholder (muted): "Ask a regulatory question…  e.g.
    What are the labeling requirements for organic produce? What does 21 CFR require for food additives?"
  - Bottom bar (14px padding, top hairline, faint dark overlay bg, flex, gap 12px, wrap):
    - **Filter** dropdown — tiny uppercase "FILTER" label + a `<select>` (Public Sans 13px, `--surface-2`
      bg, 1px `--border-hi`, radius 9px, 9px×13px padding, custom chevron). Options: "All titles" +
      all 8 titles (`Title 7 — Agriculture`, `Title 21 — Food & Drugs`, `Title 42 — Public Health`,
      `Title 10 — Energy`, `Title 14 — Aeronautics & Space`, `Title 29 — Labor`,
      `Title 40 — Environment`, `Title 49 — Transportation`).
      > **Bug fix carried in:** the original only named titles 7/21/42 and showed "Title N" for the
      > other five. Use the full 8-title name map above.
    - **Strategy** dropdown — same style. Options: "Sequential (recommended)", "Single call".
    - Flex spacer.
    - **Search button** — Public Sans 14.5px/600, white text, `linear-gradient(180deg,--accent-2,--accent)`,
      1px `--accent`, radius 10px, 11px×22px padding, search icon + "Search regulations". Hover:
      brightness 1.06 + translateY(-1px). Glow shadow `0 8px 20px -10px --accent`.
- **Example chip** (×4) — pill (radius 999px), `--surface` bg, 1px `--border`, 9px padding, Public Sans
  13.5px `--text-2`. Leading mono "?" in accent. Hover: accent border, `--text`, translateY(-1px).
  The 4 example questions:
  1. "What are the labeling requirements for organic blueberries?"
  2. "Does 21 CFR require allergen declarations on packaged foods?"
  3. "What changed in the definitions of controlled substances?"
  4. "What are OSHA's fall-protection rules for construction?"
  Clicking a chip runs the search (in prod: submit that query).
- **How-it-works cell** (×3) — panel bg, 22px padding. Mono accent step label ("STEP 01/02/03"),
  Spectral 17px/600 title, 13px muted description. Step 3 also has 3 small "register pills"
  (Plain English / Legal Language / CFR Citations) — 10.5px/600, `--surface-2`, radius 6px.
  Copy: 01 "Ask in plain English" · 02 "We retrieve the real text" (emphasis: *current eCFR edition*) ·
  03 "Three grounded answers".
- **Title tag** (×8) — `--surface` bg, 1px border, radius 8px, 7px×12px. Mono accent number + Public
  Sans 12.5px `--text-2` name.

### 2. Pipeline loading state

- **Purpose:** Show the multi-stage backend work substantively (vs. a single spinner).
- **Layout:** Masthead, then:
  - **Loader head** — Spectral 19px `--text-2`: `Answering "<the question>"` (question in `--text`).
    26px below.
  - **Pipeline** — vertical stack of step rows sharing borders (first/last rounded 12px), each row
    16px×20px padding, flex, gap 16px:
    - **Dot** (26px circle): pending = number, 1.5px `--border-hi`; active = a spinning ring
      (`--accent`); done = verified-green check on `--verified-dim`.
    - Label (Public Sans 15px/500, brightens when active) + sub (12px muted).
    - Right: mono latency ("420 ms") shown once done.
    - Active row: `--surface` bg + a 2.5px accent left-edge bar.
  - **Steps** (3): "Classifying your question" (Determining intent and scope) · "Searching the Code of
    Federal Regulations" (Retrieving grounded sections across 8 titles) · "Generating grounded answer"
    (Synthesizing three registers with verbatim quotes).
  - The original pipeline also has a temporal-only "Comparing current and prior versions…" stage — add
    it conditionally for "what changed?" queries.

### 3. Result state ← the core screen

- **Purpose:** Present the three grounded registers with trust signals up top and citations always visible.
- **Layout:**
  1. **Compact search bar** — `--surface`, 1px border, radius 12px, 12px padding. Search icon +
     question echoed (Spectral 16.5px, ellipsized) + a "All titles" select + **"New search"** button
     (resets to Home). 26px below.
  2. **Trust bar** — flex, space-between, items flex-start. 22px below.
     - **Left:** the question as an `<h1>` — **Spectral 27px/600**, line-height 1.2, letter-spacing
       -0.012em, max-width 30ch, `text-wrap: balance`.
     - **Right:** the **trust chips** (flex, wrap, gap 9px, justified end) — the confidence trio +
       Print. This trio MUST stay at the top of the result. Chips:
       - **Grounded** (a `<button>`): verified-green tint, shield-check icon, "Grounded in **8** cited
         sections", trailing small chevron. **Clicking smooth-scrolls to the citations rail and pulses
         it** (1.5s box-shadow flash). Hover: green border, lift.
       - **Fresh:** "Current as of **Apr 2026**" with a verified-green dot (3px ring glow).
       - **Confidence:** shield icon + qualitative tier text ("High confidence"). Colored by tier
         (high=green, medium=amber, low=red). **No % by default** — a precise score is available behind
         a tweak but off by default (the original % implied more calibration than exists; lead with
         grounding + freshness instead). Tooltip may show retrieval %/coverage %.
       - **Print / PDF** button (secondary style).
  3. **Result grid** — CSS grid, `minmax(0,1fr) 348px`, gap 24px, align-items start.
     - **Reading panel** (left) — `--panel`, 1px border, radius 14px, card shadow.
       - **Tab bar** (10px×16px, bottom hairline, faint dark bg): a **segmented control** with two tabs
         — "Plain English" (book icon) / "Legal Language" (scale icon). Selected segment: `--surface-hi`
         bg, raised. Far right **panel-meta** (mono 11px muted): a strategy badge ("sequential") + latency
         ("9.8s").
         > **Keep tabs + rail** (do NOT auto-stack all three). Answers get long; the rail keeps the
         > grounding always visible while tabs let the user choose Plain vs. Legal. (A "stacked" variant
         > exists as a tweak but is not the default.)
       - **Panel body** (30px 38px 38px): the **prose** — Spectral 17px, line-height 1.68, max-width 62ch.
         - `h2` = section headings: Spectral 16px/600, uppercase, letter-spacing 0.02em, **accent color**,
           bottom hairline.
         - Bulleted lists: custom accent dot markers (no native bullets).
         - Inline **citation refs** (e.g. `7 CFR § 205.300`): mono 0.82em, accent text on `--accent-dim`,
           radius 5px — appear inline in Plain-English bullets.
         - **Verbatim statute quote block** (Legal register): the gold treatment — `--gold-dim` bg, 2.5px
           **gold** left border, radius 0 10px 10px 0, 16px/18px padding. Quote text = Spectral *italic*
           16px. Below it a meta row: tiny gold uppercase "VERBATIM STATUTE" label + a faint gold rule +
           mono citation (e.g. `7 CFR § 205.300(a)`). This visually distinguishes *quoted law* from
           *synthesis*.
     - **Citations rail** (right, 348px, **sticky** top:18px) — see below.
  4. **Provenance footer** — `--surface`, 1px border, radius 12px, 15px×18px, flex, shield icon + 12px
     muted text. Exact copy (this is the required legal qualification):
     > *"Generated by **Federal Regulation Query** (regs.bradhinkel.com) from the U.S. eCFR · retrieved
     > June 3, 2026. This is informational only and not legal advice — verify against the official eCFR
     > at ecfr.gov before relying on this text."*
     `ecfr.gov` is a link; the retrieval date should be dynamic.

#### Citations rail (the grounding apparatus)

- Container: `--panel`, 1px border, radius 14px, sticky.
- **Head:** Spectral 16px/600 "Grounded sections" (nowrap) + a mono count pill ("8"); right side a small
  "eCFR ↗" link. **This mirrors the Grounded pill's language and count on purpose** — the pill, the rail
  title, and the sub-line all say "8 … sections" so the connection is unmistakable.
- **Sub:** 11px muted — "Every claim in the answer traces to one of these **8** sections."
- **List:** scrollable (max-height ~660px on desktop). Citations are **grouped by CFR title** with a
  small uppercase group label per title (e.g. "TITLE 21 — FOOD & DRUGS", "TITLE 7 — AGRICULTURE").
- **Citation card** (a button; hover = `--surface` bg + border, reveals an external-link icon top-right):
  - Accent **number chip** (mono, `--accent-dim`, 1px accent-line border).
  - **Ref line** — mono 12.5px/600 `--text` (e.g. `21 CFR § 145.120`).
  - **Heading** — Spectral 13.5px `--text-2` (e.g. "Canned berries").
  - **Agency** — 11px: agency in accent + " · " + department. (e.g. "Food and Drug Administration ·
    Department of Health and Human Services".)
  - **Freshness** — 10.5px muted with a green dot: "current as of April 9, 2026".
- **Compact density (DEFAULT):** tighter padding (9px×11px); heading + agency truncate to one line with
  ellipsis; everything still present. (A "comfortable" density is a tweak.)
- **Responsive:** below 940px the grid collapses to one column and the rail un-stickies and stacks below
  the answer (full width).

### 4. Off-topic state

- Amber notice card (`--amber-dim` bg, amber border): alert icon, Spectral 18px/600 "Outside the Code of
  Federal Regulations", 14px body explaining the tool only answers federal-regulation questions and
  suggesting a rephrase. Preceded by the echoed (greyed) question bar.

### 5. Not-found state

- Centered muted card (`--surface`, border, 50px×28px, column, centered): search-empty icon, Spectral
  18px/600 "No grounded sections found", body: it searched all 8 titles, found nothing directly on
  point, and **declines rather than guessing** — narrow scope / try a related term. This honest
  not-found is a core trust primitive; keep it prominent.

### About modal (shared)

- Centered overlay (`rgba(4,7,12,.62)` + 6px backdrop blur). Modal: `--panel`, 1px `--border-hi`, radius
  18px, max-width 540px, pop-in animation. Close "✕" (top-right) and Esc both dismiss.
- Spectral 22px/600 "About this tool", then a Spectral 15.5px product summary, a row of 3 stat cards
  ("8 CFR titles indexed" / "265K sections grounded" / "3 answer registers"), then 3 link rows: "Built
  by Brad Hinkel" (bradhinkel.com), "Source on GitHub" (repository), "Built with Claude Code"
  (claude.com/claude-code).

### Masthead (shared)

- Flex, space-between, items flex-end, bottom hairline, 30px/18px padding, 38px bottom margin.
- **Left brand:** a small "seal" mark (concentric-ring + column motif SVG, accent-colored) + wordmark
  "Federal **Regulation** Query" — Spectral 25px/600, "Regulation" in accent, nowrap. Below (indented
  41px to align past the seal): coverage line, 12px muted — "**8** CFR titles indexed · **265,641**
  sections grounded" (numbers tabular).
- **Right nav:** "About" (opens modal) and "Query history →" (13.5px, hover = `--surface-2` bg). Clicking
  the brand returns Home.

---

## Interactions & Behavior

- **Submit query:** from Home (Search button, ⌘/Ctrl+Enter in the textarea, or an example chip) →
  **loading** (staged pipeline) → **result**. In prod, drive stage progression from the backend stream
  (classify → retrieve → [compare] → generate) rather than the prototype's timers.
- **Register tabs:** clicking Plain English / Legal Language swaps the reading-panel body. Citations rail
  is unaffected (always visible).
- **Grounded pill → rail:** clicking the "Grounded in N cited sections" chip smooth-scrolls the rail into
  view and triggers a 1.5s pulse highlight (`railflash` keyframes). Use a programmatic scroll (compute
  offset + `window.scrollTo`), **not** `scrollIntoView`.
- **Citation cards:** hover reveals an external-link affordance; clicking should open the section on
  ecfr.gov (build the eCFR URL from title/part/section).
- **New search:** resets to Home. **Brand/seal:** returns Home.
- **About:** opens modal; Esc / ✕ / overlay-click closes.
- **Hover states:** buttons lift 1px + brighten; chips/cards gain accent borders; selects gain accent border.
- **Entrance:** screens fade/rise in via a transform-only animation (~0.35s). **Important:** never animate
  `opacity` from 0 for content that must be visible — some embedded/preview environments pause CSS
  animations at load and would hold content invisible. Animate transform only (or respect
  `prefers-reduced-motion: reduce`, which disables these).
- **Reduced motion:** `prefers-reduced-motion: reduce` disables entrance + spinner animations.

## Responsive Behavior

- **≤ 940px:** result grid → single column; rail un-stickies, full width below the answer; how-it-works →
  1 column; trust bar stacks (chips left-aligned under the question, question shrinks to 23px).
- **≤ 600px:** 16px side padding; masthead stacks; tighter panel padding; composer textarea 17px.
- Hit targets stay ≥ 40px.

## State Management

State variables the UI needs (names from the prototype; map to your data layer):
- `screen`: `home | loading | result | offtopic | notfound` — the lifecycle stage (in prod, derived from
  request status + classification result).
- `register`: `plain | legal` — active reading tab (citations are always shown).
- `aboutOpen`: boolean — About modal.
- The answer payload per query: `query`, `strategy`, `latencyMs`, `confidence { tier, score, retrieval,
  coverage }`, `plain[]` (prose blocks), `legal[]` (prose blocks incl. verbatim quotes), `citations[]`
  (`ref, heading, agency, dept, date, titleNum, titleName`), and the pipeline stage list. See `data.js`
  for the exact shape used by the prototype.
- **Tweak/theme prefs** (optional to ship; see Tweaks): `theme`, `accent`, `headlineSerif`, `registers`,
  `citationDensity`, `showPct`. At minimum ship the *defaults*: dark, blue, serif headlines, tabs+rail,
  compact citations, confidence-% hidden.

---

## Design Tokens

All tokens are defined as CSS variables in `styles.css` (`:root` for dark, `[data-theme="light"]` for
light). Implement as Tailwind theme tokens or CSS variables.

### Colors — Dark (default)
| Token | Value | Use |
|---|---|---|
| `--bg` | `#0a0e16` | page background (deep ink-navy); a radial top-glow to `#0c1119` sits on top |
| `--panel` | `#10151f` | answer panel / rail / modal |
| `--surface` | `#141b27` | cards, chips, search bar, provenance |
| `--surface-2` | `#1a2230` | selects, badges, register pills |
| `--surface-hi` | `#1f2937` | selected segment |
| `--border` | `#232d3e` | hairlines |
| `--border-soft` | `rgba(255,255,255,.07)` | inner hairlines |
| `--border-hi` | `#2e3a4f` | stronger borders / inputs |
| `--text` | `#e9edf4` | primary text |
| `--text-2` | `#aab4c4` | secondary |
| `--text-3` | `#707d92` | tertiary / meta |
| `--muted` | `#5d6a7e` | faint labels |
| `--accent` | `#5183ff` | blue: links, primary button, section headings, citation numbers |
| `--accent-2` | `#6f9bff` | button gradient top / hover |
| `--accent-dim` | `rgba(81,131,255,.14)` | accent tints |
| `--accent-line` | `rgba(81,131,255,.4)` | accent borders |
| `--verified` | `#56b78f` | grounding/freshness/high-confidence green |
| `--verified-dim` | `rgba(86,183,143,.13)` | green tint |
| `--gold` | `#cba85f` | **verbatim statute quotes only** |
| `--gold-dim` | `rgba(203,168,95,.1)` | quote bg |
| `--gold-line` | `rgba(203,168,95,.42)` | quote left border / rule |
| `--amber` | `#d6a441` | off-topic notice |
| `--amber-dim` | `rgba(214,164,65,.12)` | off-topic bg |
| `--red` | `#e36a7d` | error / low-confidence |
| `--red-dim` | `rgba(227,106,125,.12)` | error bg |

### Colors — Light ("warm paper")
| Token | Value |
|---|---|
| `--bg` | `#f4f1ea` (top-glow to `#efebe1`) |
| `--panel` | `#ffffff` |
| `--surface` | `#faf8f3` |
| `--surface-2` | `#f1ede4` |
| `--surface-hi` | `#ece7db` |
| `--border` | `#ddd6c8` |
| `--border-hi` | `#cabf9f` |
| `--text` | `#211c12` |
| `--text-2` | `#544d3c` |
| `--text-3` | `#837a64` |
| `--muted` | `#9a9079` |
| `--accent` | `#2d5fd6` (`--accent-2` `#2451bd`) |
| `--verified` | `#2f8a63` |
| `--gold` | `#9a7724` (`--gold-line` `rgba(154,119,36,.4)`) |
| `--amber` | `#a9781a` · `--red` `#c0445a` |

### Alternate accents (tweak options — same dim/line pattern at .14/.4)
`#5183ff` federal blue (default) · `#3f6ddb` navy · `#2f9c7a` federal green · `#b07d3a` bronze.

### Typography
| Family | Weights | Use |
|---|---|---|
| **Public Sans** | 400/500/600/700 | UI, labels, meta, buttons, nav, chips |
| **Spectral** | 400/500/600/700 + italic 400/500 | headlines, question, answer prose, modal/section heads |
| **IBM Plex Mono** | 400/500/600 | citation `§` refs, latency/strategy meta, step numbers |

Key sizes: wordmark 25px · question `h1` 27px (23px ≤940px) · answer prose 17px/1.68 · section `h2`
16px uppercase accent · verbatim quote italic 16px/1.62 · citation ref 12.5px mono · UI body 13–14px ·
meta/labels 10–12px (uppercase labels: 700, letter-spacing 0.1–0.16em).

### Spacing / radius / shadow
- Column max-width **1080px**, side padding 28px (16px mobile). Rail width **348px**, grid gap 24px.
- Radii: cards/panels **14px**, modal **18px**, inputs/buttons/chips **7–10px**, pills/segments **6–9px**,
  full-pill **999px**.
- Card shadow: `0 1px 0 rgba(255,255,255,.03) inset, 0 14px 40px -20px rgba(0,0,0,.7)` (dark).
  Modal/pop shadow: `0 30px 80px -24px rgba(0,0,0,.8)`.
- Section rhythm on Home: composer→note 13px, →examples 22px, →how-it-works 44px, →coverage 40px.

---

## Assets

- **No external image assets.** All icons are inline SVGs (single `Ico` component with a path map in
  `ui.jsx`): search, chevron, scale, book, list, check, shield, shield-check, clock, printer, external-
  link, edit, spark, alert, empty, arrow. The "seal" is a small inline SVG (concentric rings + column
  motif) — decorative/original, **not** a real government seal; swap for the project's mark if desired.
- **Fonts:** Google Fonts (Spectral, Public Sans, IBM Plex Mono). In the prototype they load via a
  `<link>`; in production self-host or use `next/font`.
- **Tweaks panel** (`tweaks-panel.jsx`) is a prototype-only authoring tool — **do not ship it.**

---

## Files (in this bundle)

| File | What it is |
|---|---|
| `Federal Regulation Query.html` | Entry point — loads fonts, React/Babel, and the scripts below. Open this to view the prototype. |
| `styles.css` | **The source of truth for all visual tokens & component styling** (dark + light). |
| `data.js` | Mock answer payload (the "organic blueberries" demo), CFR title list, examples, pipeline stages. Shows the data shapes the UI expects. |
| `ui.jsx` | Icon set (`Ico`/`Seal`) + the `Field` dropdown primitive. |
| `screens.jsx` | All screen components: `Masthead`, `Prose`/`Block` renderer, `CitationsRail`/`CiteCard`, `ResultView`, `StackedRegisters`, `Loader`, `OffTopic`, `NotFound`, `AboutModal`, `Provenance`. |
| `app.jsx` | `Home` screen, the `App` state machine, theme/accent application, and Tweaks wiring (prototype-only). |
| `tweaks-panel.jsx` | Prototype authoring panel — **not for production.** |

### How to view
Open `Federal Regulation Query.html` in a browser (it fetches CDN React/Babel + Google Fonts, so it needs
network). Use the Tweaks panel (if the host exposes it) to preview light theme, accents, density, and the
five screen states.

---

## Implementation checklist (defaults to ship)

- [ ] Dark theme default; light theme available via `data-theme`.
- [ ] Public Sans / Spectral / IBM Plex Mono wired (self-hosted or `next/font`).
- [ ] Federal-blue accent `#5183ff`.
- [ ] **Tabs + persistent citations rail** (not stacked). Plain-English / Legal-Language segmented tabs.
- [ ] Legal register in **serif** with **gold verbatim-quote blocks** (replaces the old monospace).
- [ ] Trust trio at top: Grounded (click → scroll+pulse rail) · Current-as-of · qualitative confidence.
      **Confidence % hidden by default.**
- [ ] Citations **grouped by title**, **compact** density default, agency + "current as of" as real
      metadata, link out to ecfr.gov.
- [ ] Staged pipeline loader driven by the backend stages.
- [ ] eCFR **provenance footer** on results + the home disclaimer note.
- [ ] Full 8-title filter name map (fixes the original "Title N" bug).
- [ ] Honest **not-found** and **off-topic** states preserved.
- [ ] Responsive collapse at 940/600px.
