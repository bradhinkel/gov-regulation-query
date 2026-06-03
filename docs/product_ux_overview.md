# Government Regulation Query — Product & UX Overview

*For a UX design pass. Describes the product, the current UI (every screen, component,
and state), the visual system, and where polish would matter most.*

---

## 1. Product overview

**What it is.** A web app that answers natural-language questions about U.S. federal
regulations (the Code of Federal Regulations) using retrieval-augmented generation.
Live at **regs.bradhinkel.com**.

**Who it's for.** Compliance officers, paralegals, journalists, students, and
curious citizens who need to understand a federal rule without parsing legalese.

**What's distinctive — the "reliability" thesis.** Unlike a general chatbot, every
answer is grounded in the actual regulatory text and is designed to be *verifiable*:

- **Three registers per answer.** (1) **Plain-English** explanation, (2) **Legal /
  regulatory language** synthesis with verbatim quotes, (3) **structured CFR
  citations** (Title / Part / Section).
- **Freshness.** The corpus is kept current via a versioned-replacement pipeline;
  each citation shows the edition it's **"current as of."**
- **Knows when it doesn't know.** A confidence signal and an explicit *not-found*
  state — it declines rather than fabricates.
- **Temporal awareness.** "What changed?" questions return a before/after comparison
  of current vs. archived regulatory text.
- **Coverage.** 8 major CFR titles (~265,000 sections): Agriculture, Food & Drugs,
  Public Health, Energy, Aeronautics, Labor, Environment, Transportation.

**The design north star:** trust and verifiability. A paraphrase that swaps "may"
for "must" is a material misstatement of law — the UI should make *provenance,
freshness, and grounding* feel first-class, not like afterthoughts.

---

## 2. Tech & theming constraints (for the designer)

- **Stack:** Next.js 14 (App Router) + TypeScript + Tailwind CSS. Client-rendered.
- **Theme:** dark, single centered column (`max-w-3xl`, ~768px), defined by CSS
  variables in `frontend/app/globals.css` — **easy to retheme globally**:

  | Token | Value | Use |
  |---|---|---|
  | `--background` | `#0d1117` | page background (near-black) |
  | `--foreground` | `#e2e8f0` | primary text |
  | `--accent` / `--accent-dark` | `#3b82f6` / `#2563eb` | blue — links, buttons, headings |
  | `--surface` / `--surface-2` | `#161b22` / `#21262d` | cards / inputs |
  | `--border` | `#30363d` | hairlines |
  | `--muted` | `#6b7280` | secondary text |
  | font | Inter / Segoe UI | — |

- Components are small and isolated (`frontend/app/components/`), so restyling is
  low-risk. A print stylesheet already exists (`.no-print` / `.print-only`).

---

## 3. Screens & components (current state)

### 3.1 Home (`/`) — the main screen

**Header.** App title "Federal Regulation Query" (blue, bold). A dynamic subtitle:
"8 CFR titles indexed — 265,641 sections." Top-right: **About** (opens modal) and
**Query history →** (link).

**Query form** (`QueryForm.tsx`).
- A 3-row **textarea** with an example-laden placeholder.
- A control row: **title filter** dropdown ("All titles" / "Title 7 — Agriculture"…),
  a **strategy** dropdown ("Sequential (recommended)" / "Single call"), and a
  right-aligned blue **Search** button (label flips to "Searching regulations…").

**Status banner** (`StatusBanner.tsx`) — shown while working or on a non-result outcome:
- Spinner + message for pipeline stages: *Checking your question…* (classifying) →
  *Searching the Code of Federal Regulations…* (retrieving) → *Comparing current
  and prior versions…* (temporal only) → *Generating…*.
- **Off-topic**: amber box — "This system answers questions about U.S. federal
  regulations. Please rephrase…".
- **Error**: red box.

**Result area** (when an answer arrives):
- A header row: the user's question in quotes (left) and, on the right, an optional
  purple **"Change comparison"** badge (temporal answers), a **confidence badge**,
  and a **Print / Save as PDF** button.
- **Response panel** (`ResponsePanel.tsx`) — a card with a **tab bar**: *Plain
  English* · *Legal Language* · *CFR Citations (N)*. Far right of the tab bar shows
  strategy + latency (e.g., "sequential 9700ms"). Tab content:
  - **Plain English** — prose.
  - **Legal Language** — formal synthesis, currently rendered in **monospace**.
  - **CFR Citations** — numbered list; each shows the reference (e.g., `40 CFR
    § 86.1818-12`), section heading, **agency** (blue), and **"current as of
    May 27, 2026"** (muted).
- **Not-found** state: a centered, muted message card ("No relevant regulations
  were found…").

**Confidence badge** (`ConfidenceBadge` in `page.tsx`). A small pill colored by tier
— **high=green, medium=yellow, low=red** — showing the tier and a score %. Hover
tooltip shows retrieval % and citation-coverage %.
> Note: our evaluation (see `confidence_calibration_findings.md`) found the
> high/medium/low gradient is **not** a strongly calibrated quality probability;
> the trustworthy primitives are *not-found*, *citations*, and *current-as-of*.
> Design should de-emphasize a precise % and emphasize grounding/freshness.

### 3.2 About modal (`AboutModal.tsx`)
Centered overlay: a one-paragraph product summary + three link rows — *Built by
Brad Hinkel* (bradhinkel.com), *Source on GitHub*, *Built with Claude Code*.

### 3.3 History (`/history`)
Header "Query History" + "← Back". A count ("N total queries") and a list of cards:
each shows the question, a 3-line clamp of the plain-English answer (or "Not found"),
and a meta row — timestamp · citation count · latency · colored tier·%.

### 3.4 Print / Save-as-PDF (`PrintableResult.tsx`)
A clean, light-background print document (hidden on screen): title, the question,
all three registers in sequence, the citation list with "current as of" dates, and
a provenance footer. Triggered by the Print button; uses the browser's native
"Save as PDF."

---

## 4. Full state list (what to screenshot)

| # | State | How to trigger |
|---|---|---|
| 1 | Home, idle (empty form) | load `/` |
| 2 | Loading stages | submit a query (capture spinner; stages flip fast) |
| 3 | Result — Plain English tab | ask "What are the labeling requirements for organic produce?" |
| 4 | Result — Legal Language tab | switch tab |
| 5 | Result — CFR Citations tab | switch tab (shows agency + "current as of") |
| 6 | Confidence badge — high / medium / low | various queries |
| 7 | Temporal result + "Change comparison" badge | "What changed in the definitions relating to controlled substances?" |
| 8 | Off-topic (amber) | "What's the best restaurant in Seattle?" |
| 9 | Not-found result | an obscure non-covered topic |
| 10 | Error banner | (rare) backend error |
| 11 | About modal | click About |
| 12 | Print / PDF preview | click Print → browser print dialog |
| 13 | History page | click Query history |

---

## 5. Where polish would matter most (suggested focus)

These are honest rough edges — prioritize as you see fit:

1. **Make the three-register value prop visible at a glance.** Tabs hide two of the
   three outputs; a first-time user may not realize all three exist. Consider
   showing all three (stacked/sectioned) or a stronger affordance.
2. **Elevate freshness & provenance.** "Current as of" dates, agency, and verbatim
   quotes are the core differentiators but currently read as small muted text.
   These deserve to feel like trust signals.
3. **Rethink the confidence display.** Per our calibration finding, lead with
   *grounded citations* and *not-found honesty* rather than a precise % that implies
   more calibration than exists.
4. **Legal Language readability.** Monospace makes a prose synthesis hard to read;
   verbatim quotes vs. synthesis could be visually distinguished instead.
5. **Pipeline progress.** The backend streams distinct stages
   (classify → retrieve → [compare] → generate) — a staged progress indicator would
   feel more substantial than a single spinner line.
6. **Empty / first-run state.** Only a placeholder guides new users; example-question
   chips or a short "how it works" could help.
7. **Citations density & scannability.** The list can get long; grouping by title,
   collapsible detail, or links out to ecfr.gov could help.
8. **Visual hierarchy & spacing.** The layout is functional but flat; typographic
   scale, section dividers, and rhythm could lift it.
9. **Mobile.** Verify the control row, tabs, and citation list hold up at small widths.
10. **Known bug to fix (not design):** the title-filter dropdown only names Titles 7/
    21/42; the other five show "Title N". Needs the full 8-title name map.

---

## 6. One-paragraph product summary (reusable)

> Government Regulation Query is a retrieval-augmented generation system over the
> U.S. Code of Federal Regulations. Ask a plain-English question and get three
> grounded answers — a plain-English explanation, a formal legal-language synthesis
> with verbatim quotes, and precise CFR citations — each tied to the current eCFR
> edition. It spans 8 major CFR titles (~265,000 sections), shows a confidence
> signal and an explicit not-found state, answers "what changed?" with current-vs-
> prior comparisons, and stays current through an automated versioned-replacement
> pipeline.
