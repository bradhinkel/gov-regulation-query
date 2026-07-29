// parseAnswer — turn the backend's markdown prose strings into the design's
// block model. The backend emits markdown: `#`/`##` headings, `**bold**`,
// `*italic*`, `- bullets`, and inline verbatim quotes of the form
//   "quoted statutory text" (7 CFR § 990.3(a)(2)(i))
// For the LEGAL register those quotes are lifted into gold "Verbatim statute"
// blocks; elsewhere parenthesized citations become inline accent chips.

import type { Block } from "./types";

// A CFR citation, including nested subsection parens like (a)(2)(i).
const CFR = String.raw`\d+\s+CFR\s+§?\s*[\d.]+(?:\([a-zA-Z0-9]+\))*`;
// A Federal Register citation ("91 FR 47162") or docket ID — Part C
// forward-looking answers cite these instead of CFR sections.
const FR = String.raw`\d+\s+FR\s+\d+`;
const CITE = String.raw`(?:${CFR}|${FR})`;
const CFR_PAREN_RE = new RegExp(String.raw`\(\s*(${CITE})\s*\)`, "g");
// A quoted span immediately followed by a parenthesized citation.
const VERBATIM_RE = new RegExp(
  String.raw`[“"]([^“”"]+)[”"]\s*\(\s*(${CITE})\s*\)`,
  "g"
);
const TRAILING_CITE_RE = new RegExp(String.raw`\(\s*(${CITE})\s*\)\.?\s*$`);

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Inline markdown → safe HTML (bold, italic, quoted terms, citation chips).
function inline(raw: string): string {
  let s = esc(raw.trim());
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
  // Short quoted terms (e.g. "organic") read better italicised, as in the design.
  s = s.replace(/[“"]([^“”"]{1,60})[”"]/g, "<em>“$1”</em>");
  // Parenthesized CFR citations → inline accent chips (parens dropped).
  s = s.replace(CFR_PAREN_RE, '<span class="cite-ref">$1</span>');
  return s;
}

function isBullet(line: string): boolean {
  return /^\s*[-*•]\s+/.test(line) || /^\s*\d+\.\s+/.test(line);
}

function bulletItem(content: string): { html: string; cite?: string } {
  const trimmed = content.trim();
  const m = trimmed.match(TRAILING_CITE_RE);
  if (m && m.index !== undefined) {
    return { html: inline(trimmed.slice(0, m.index)), cite: m[1].trim() };
  }
  return { html: inline(trimmed) };
}

// Drop punctuation orphaned when a quote sentence is lifted out (e.g. ". This …").
function cleanFragment(s: string): string {
  return s.trim().replace(/^[.,;:]\s*/, "").trim();
}

// Legal paragraph: interleave synthesis prose (<p>) with gold verbatim blocks.
function pushLegalParagraph(blocks: Block[], text: string): void {
  const re = new RegExp(VERBATIM_RE.source, "g");
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const before = cleanFragment(text.slice(last, m.index));
    if (before) blocks.push({ t: "p", html: inline(before) });
    blocks.push({ t: "quote", text: m[1].trim(), cite: m[2].trim() });
    last = m.index + m[0].length;
  }
  const after = cleanFragment(text.slice(last));
  if (after) blocks.push({ t: "p", html: inline(after) });
}

export function parseAnswer(text: string, mode: "plain" | "legal"): Block[] {
  if (!text || !text.trim()) return [];
  const lines = text.replace(/\r/g, "").split("\n");
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }

    // Heading
    const h = line.match(/^\s*(#{1,6})\s+(.*)$/);
    if (h) {
      const level = h[1].length;
      blocks.push({
        t: level <= 2 ? "h2" : "h3",
        html: inline(h[2].replace(/\*\*/g, "").replace(/[:.]\s*$/, "")),
      });
      i++;
      continue;
    }

    // Bullet list
    if (isBullet(line)) {
      const items: { html: string; cite?: string }[] = [];
      while (i < lines.length && lines[i].trim()) {
        if (isBullet(lines[i])) {
          const content = lines[i]
            .replace(/^\s*[-*•]\s+/, "")
            .replace(/^\s*\d+\.\s+/, "");
          items.push(bulletItem(content));
        } else if (items.length && /^\s{2,}\S/.test(lines[i])) {
          // indented continuation of the previous bullet
          items[items.length - 1].html += " " + inline(lines[i]);
        } else {
          break;
        }
        i++;
      }
      blocks.push({ t: "ul", items });
      continue;
    }

    // Paragraph — gather consecutive non-blank, non-special lines
    const para: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !isBullet(lines[i]) &&
      !/^\s*#{1,6}\s+/.test(lines[i])
    ) {
      para.push(lines[i].trim());
      i++;
    }
    const paraText = para.join(" ");
    if (mode === "legal") {
      pushLegalParagraph(blocks, paraText);
    } else {
      blocks.push({ t: "p", html: inline(paraText) });
    }
  }

  // Mark the very first paragraph as the muted lead.
  if (blocks.length && blocks[0].t === "p") {
    (blocks[0] as { lead?: boolean }).lead = true;
  }
  return blocks;
}
