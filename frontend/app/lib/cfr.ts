// CFR title metadata + helpers (title→name map, eCFR link-out, date formatting).
import type { Citation, SourceTitle } from "./types";

// Full 8-title name map — fixes the original "Title N" bug that only named 7/21/42.
export const CFR_TITLES: { num: number; name: string }[] = [
  { num: 7, name: "Agriculture" },
  { num: 21, name: "Food & Drugs" },
  { num: 42, name: "Public Health" },
  { num: 10, name: "Energy" },
  { num: 14, name: "Aeronautics & Space" },
  { num: 29, name: "Labor" },
  { num: 40, name: "Environment" },
  { num: 49, name: "Transportation" },
];

const TITLE_NAME: Record<number, string> = Object.fromEntries(
  CFR_TITLES.map((t) => [t.num, t.name])
);

/** "Title 21 — Food & Drugs" (falls back to "Title N" if unknown). */
export function titleLabel(num?: number): string {
  if (num == null) return "Other";
  const name = TITLE_NAME[num];
  return name ? `Title ${num} — ${name}` : `Title ${num}`;
}

/** Build the canonical eCFR.gov URL for a citation. */
export function ecfrUrl(c: Citation): string {
  const base = "https://www.ecfr.gov/current";
  if (c.title_number == null) return "https://www.ecfr.gov";
  let url = `${base}/title-${c.title_number}`;
  if (c.part_number) url += `/part-${c.part_number}`;
  if (c.section_number) url += `/section-${c.section_number}`;
  return url;
}

/** Parse an eCFR date string ("2026-04-09" or ISO) into a Date, or null. */
function toDate(date?: string): Date | null {
  if (!date) return null;
  const d = new Date(date.length <= 10 ? date + "T00:00:00" : date);
  return isNaN(d.getTime()) ? null : d;
}

/** "April 9, 2026" */
export function formatLongDate(date?: string): string | null {
  const d = toDate(date);
  return d
    ? d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })
    : null;
}

/** "Apr 2026" — used for the compact "Current as of" trust chip. */
export function formatShortMonth(date?: string): string | null {
  const d = toDate(date);
  return d ? d.toLocaleDateString("en-US", { year: "numeric", month: "short" }) : null;
}

/** The most-recent effective date across a set of citations (the answer's freshness). */
export function latestCitationDate(citations: Citation[]): string | undefined {
  let best: string | undefined;
  for (const c of citations) {
    const d = toDate(c.effective_date);
    if (d && (!best || d > (toDate(best) as Date))) best = c.effective_date;
  }
  return best;
}

// Title-case a SHOUTING agency string, keeping connector words lowercase.
const SMALL_WORDS = new Set(["of", "the", "and", "for", "to", "in", "on", "a", "an"]);
function titleCaseWords(s: string): string {
  return s
    .toLowerCase()
    .replace(/\b[a-z][a-z'.]*/g, (word, offset: number) => {
      if (offset > 0 && SMALL_WORDS.has(word)) return word;
      return word.charAt(0).toUpperCase() + word.slice(1);
    });
}

/**
 * Split + tidy the eCFR agency string for the citations rail. The raw field is
 * ALL-CAPS and crams the department in (e.g.
 *   "AGRICULTURAL MARKETING SERVICE (...), DEPARTMENT OF AGRICULTURE")
 * so we recover the design's tidy "Agency · Department" two-part line — no
 * backend change. Returns null when there's nothing to show.
 */
export function formatAgency(raw?: string): { agency: string; department?: string } | null {
  if (!raw || !raw.trim()) return null;
  let agency = raw.trim();
  let department: string | undefined;

  const m = agency.match(/,?\s*DEPARTMENT OF .+$/i);
  if (m && m.index !== undefined) {
    department = titleCaseWords(agency.slice(m.index).replace(/^,?\s*/, "").trim());
    agency = agency.slice(0, m.index).replace(/,\s*$/, "").trim();
  }
  // Drop the bureaucratic sub-office parenthetical for a clean trust signal.
  agency = agency.replace(/\s*\([^)]*\)/g, "").replace(/,\s*$/, "").trim();

  return { agency: titleCaseWords(agency), department };
}

/** Corpus-wide freshness date from /sources (max latest_date). */
export function corpusUpdatedDate(sources: SourceTitle[]): string | undefined {
  let best: string | undefined;
  for (const s of sources) {
    const d = toDate(s.latest_date);
    if (d && (!best || d > (toDate(best) as Date))) best = s.latest_date;
  }
  return best;
}
