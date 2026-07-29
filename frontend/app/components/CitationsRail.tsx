"use client";

import type { Citation, FRDocument } from "../lib/types";
import { ecfrUrl, formatAgency, formatLongDate, titleLabel } from "../lib/cfr";
import { Ico } from "./Icons";

interface CitationsRailProps {
  citations: Citation[];
  frDocuments?: FRDocument[] | null;
  compact?: boolean;
}

const STATUS_LABEL: Record<string, string> = {
  proposed: "Proposed",
  "comment-open": "Comment period open",
  pending: "Pending final action",
  "final-not-yet-codified": "Final — not yet codified",
};

interface Group {
  titleNum?: number;
  name: string;
  items: { c: Citation; n: number }[];
}

export default function CitationsRail({ citations, frDocuments, compact = true }: CitationsRailProps) {
  const frDocs = frDocuments ?? [];
  const total = citations.length + frDocs.length;
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
          {frDocs.length > 0 ? "Cited sources" : "Grounded sections"}{" "}
          <span className="count">{total}</span>
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
        Every claim in the answer traces to one of these <b>{total}</b> sources.
      </div>
      <div className="rail-list">
        {frDocs.length > 0 && (
          <div>
            <div className="title-group-label">Federal Register — proposed &amp; upcoming</div>
            {frDocs.map((d, i) => (
              <FRDocCard key={d.document_number ?? i} d={d} n={citations.length + i + 1} />
            ))}
          </div>
        )}
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

function FRDocCard({ d, n }: { d: FRDocument; n: number }) {
  const status = STATUS_LABEL[d.status] ?? d.status;
  const closes = formatLongDate(d.comments_close_on ?? undefined);
  const effective = formatLongDate(d.effective_on ?? undefined);
  const docket = d.dockets?.[0];
  return (
    <a
      className="cite-card fr-card"
      href={d.url}
      target="_blank"
      rel="noopener noreferrer"
    >
      <span className="ext">
        <Ico name="ext" />
      </span>
      <div className="cc-top">
        <span className="cite-num">{n}</span>
        <div className="cite-main">
          <div className="cite-ref-line">
            {d.fr_citation ?? d.document_number}
            <span className={"status-badge s-" + d.status}>{status}</span>
          </div>
          {d.title && <div className="cite-heading">{d.title}</div>}
          {d.agencies?.length ? <div className="cite-agency"><span className="ag">{d.agencies[0]}</span></div> : null}
          {(closes || effective || d.cfr_references?.length) && (
            <div className="cite-fresh">
              {closes && <>comments close {closes}</>}
              {!closes && effective && <>effective {effective}</>}
              {d.cfr_references?.length ? (
                <>
                  {closes || effective ? " · " : ""}
                  affects {d.cfr_references.slice(0, 2).join(", ")}
                </>
              ) : null}
            </div>
          )}
          {docket && (
            <div className="cite-agency">
              docket{" "}
              <span className="ag">{docket.docket_id}</span>
            </div>
          )}
        </div>
      </div>
    </a>
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
