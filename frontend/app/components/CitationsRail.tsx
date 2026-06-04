"use client";

import type { Citation } from "../lib/types";
import { ecfrUrl, formatAgency, formatLongDate, titleLabel } from "../lib/cfr";
import { Ico } from "./Icons";

interface CitationsRailProps {
  citations: Citation[];
  compact?: boolean;
}

interface Group {
  titleNum?: number;
  name: string;
  items: { c: Citation; n: number }[];
}

export default function CitationsRail({ citations, compact = true }: CitationsRailProps) {
  // Group by CFR title, preserving order of first appearance; number globally.
  const groups: Group[] = [];
  const seen = new Map<number, Group>();
  citations.forEach((c, idx) => {
    const key = c.title_number ?? -1;
    let g = seen.get(key);
    if (!g) {
      g = { titleNum: c.title_number, name: titleLabel(c.title_number), items: [] };
      seen.set(key, g);
      groups.push(g);
    }
    g.items.push({ c, n: idx + 1 });
  });

  return (
    <aside id="citations-rail" className={"rail" + (compact ? " compact" : "")}>
      <div className="rail-head">
        <span className="rail-title">
          <Ico name="shieldcheck" style={{ width: 16, height: 16, color: "var(--verified)" }} />
          Grounded sections <span className="count">{citations.length}</span>
        </span>
        <a
          href="https://www.ecfr.gov"
          target="_blank"
          rel="noopener noreferrer"
          style={{ fontSize: 11, color: "var(--text-3)", display: "inline-flex", alignItems: "center", gap: 5 }}
          title="Open on eCFR.gov"
        >
          eCFR <Ico name="ext" style={{ width: 11, height: 11 }} />
        </a>
      </div>
      <div className="rail-sub">
        Every claim in the answer traces to one of these <b>{citations.length}</b> sections.
      </div>
      <div className="rail-list">
        {groups.map((g, gi) => (
          <div key={gi}>
            <div className="title-group-label">{g.name}</div>
            {g.items.map(({ c, n }) => (
              <CiteCard key={n} c={c} n={n} />
            ))}
          </div>
        ))}
      </div>
    </aside>
  );
}

function CiteCard({ c, n }: { c: Citation; n: number }) {
  const date = formatLongDate(c.effective_date);
  const ag = formatAgency(c.agency);
  return (
    <a className="cite-card" href={ecfrUrl(c)} target="_blank" rel="noopener noreferrer">
      <span className="ext">
        <Ico name="ext" />
      </span>
      <div className="cc-top">
        <span className="cite-num">{n}</span>
        <div className="cite-main">
          <div className="cite-ref-line">{c.cfr_reference}</div>
          {c.section_heading && <div className="cite-heading">{c.section_heading}</div>}
          {ag && (
            <div className="cite-agency">
              <span className="ag">{ag.agency}</span>
              {ag.department ? <> · {ag.department}</> : null}
            </div>
          )}
          {date && (
            <div className="cite-fresh">
              <span className="fdot" />
              current as of {date}
            </div>
          )}
        </div>
      </div>
    </a>
  );
}
