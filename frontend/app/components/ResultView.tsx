"use client";

import { useMemo, useState } from "react";
import type { QueryResult } from "../lib/types";
import { parseAnswer } from "../lib/parseAnswer";
import {
  CFR_TITLES,
  formatLongDate,
  formatShortMonth,
  latestCitationDate,
  titleLabel,
} from "../lib/cfr";
import { Ico } from "./Icons";
import Field from "./Field";
import Prose from "./Prose";
import CitationsRail from "./CitationsRail";

interface ResultViewProps {
  data: QueryResult;
  corpusDate?: string;
  titleFilter: number | null;
  onNew: () => void;
  onRefilter: (titleNumber: number | null) => void;
}

const CONF_LABEL: Record<string, string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
};

export default function ResultView({
  data,
  corpusDate,
  titleFilter,
  onNew,
  onRefilter,
}: ResultViewProps) {
  const [reg, setReg] = useState<"plain" | "legal">("plain");

  const plainBlocks = useMemo(() => parseAnswer(data.plain_english, "plain"), [data.plain_english]);
  const legalBlocks = useMemo(() => parseAnswer(data.legal_language, "legal"), [data.legal_language]);

  const conf = data.confidence;
  const q = data.quality;
  const tier = conf?.tier ?? "medium";
  const confLabel = CONF_LABEL[tier] ?? "Confidence";
  const fresh = formatShortMonth(latestCitationDate(data.citations));

  const titleOptions = [
    { value: "", label: "All titles" },
    ...CFR_TITLES.map((t) => ({ value: String(t.num), label: titleLabel(t.num) })),
  ];

  const flashRail = () => {
    const el = document.getElementById("citations-rail");
    if (!el) return;
    const y = el.getBoundingClientRect().top + window.scrollY - 76;
    window.scrollTo({ top: Math.max(0, y), behavior: "smooth" });
    el.classList.remove("flash");
    void el.offsetWidth; // restart animation
    el.classList.add("flash");
    setTimeout(() => el.classList.remove("flash"), 1500);
  };

  return (
    <div className="fade-in">
      {/* compact search bar */}
      <div className="searchbar no-print">
        <Ico name="search" className="icon" style={{ width: 18, height: 18 }} />
        <span className="q-text">{data.query}</span>
        <Field
          value={titleFilter == null ? "" : String(titleFilter)}
          options={titleOptions}
          aria-label="Filter by CFR title"
          onChange={(v) => onRefilter(v ? parseInt(v, 10) : null)}
        />
        <button className="btn-edit" onClick={onNew}>
          New search
        </button>
      </div>

      {/* trust bar — confidence/grounding/freshness trio up top */}
      <div className="trustbar">
        <h1 className="answer-q">{data.query}</h1>
        <div className="trust-chips">
          {data.temporal && (
            <span className="trust-chip" title="Temporal change comparison">
              <Ico name="clock" />Change comparison
            </span>
          )}
          <button
            className="trust-chip grounded"
            onClick={flashRail}
            title={`Jump to the ${data.citations.length} cited sections`}
          >
            <Ico name="shieldcheck" />
            Grounded in <b>{data.citations.length}</b> cited sections
            <Ico name="chevron" className="jump" />
          </button>
          {fresh && (
            <span className="trust-chip fresh">
              <span className="dot" />
              Current as of <b>{fresh}</b>
            </span>
          )}
          {conf && (
            <span
              className={"trust-chip conf-" + tier}
              title={
                q?.judge_grounding != null
                  ? `Verified by grounding judge (${q.judge_grounding}/5): ${q.judge_justification ?? ""}`
                  : `Retrieval ${Math.round(conf.retrieval_score * 100)}% · Citation coverage ${Math.round(
                      conf.citation_coverage * 100
                    )}%`
              }
            >
              <Ico name="shield" />
              {confLabel}
              {q?.judge_grounding != null && <> · verified</>}
            </span>
          )}
          <button className="btn-print" onClick={() => window.print()}>
            <Ico name="printer" />Print / PDF
          </button>
        </div>
      </div>

      <div className="result-grid">
        <section className="panel">
          <div className="panel-tabbar">
            <div className="seg">
              <button aria-selected={reg === "plain"} onClick={() => setReg("plain")}>
                <Ico name="book" className="ico" />
                Plain English
              </button>
              <button aria-selected={reg === "legal"} onClick={() => setReg("legal")}>
                <Ico name="scale" className="ico" />
                Legal Language
              </button>
            </div>
            <span className="panel-meta">
              <span className="badge">{data.strategy_used}</span>
              <span>{(data.latency_ms / 1000).toFixed(1)}s</span>
            </span>
          </div>
          <div className="panel-body">
            <Prose blocks={reg === "plain" ? plainBlocks : legalBlocks} />
          </div>
        </section>
        <CitationsRail citations={data.citations} />
      </div>

      {q?.judge_justification && (
        <div className="provenance no-print">
          <Ico name="shieldcheck" />
          <span>
            <b>Grounding verified</b> ({q.judge_grounding}/5): {q.judge_justification}
          </span>
        </div>
      )}

      <FeedbackRow queryId={data.id} />
      <Provenance corpusDate={corpusDate} retrievedAt={data.created_at} />
    </div>
  );
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";

function FeedbackRow({ queryId }: { queryId: string }) {
  const [sent, setSent] = useState<"up" | "down" | null>(null);

  const vote = async (v: "up" | "down") => {
    setSent(v); // optimistic — the signal is advisory, not transactional
    try {
      await fetch(`${API_URL}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: queryId, vote: v }),
      });
    } catch {
      /* ignore — feedback is best-effort */
    }
  };

  return (
    <div className="feedback-row no-print">
      {sent ? (
        <span className="feedback-thanks">
          Thank you — your feedback improves future answers.
        </span>
      ) : (
        <>
          <span>Was this answer helpful?</span>
          <button className="btn-edit" onClick={() => vote("up")} aria-label="Helpful">
            Yes
          </button>
          <button className="btn-edit" onClick={() => vote("down")} aria-label="Not helpful">
            No
          </button>
        </>
      )}
    </div>
  );
}

function Provenance({ corpusDate, retrievedAt }: { corpusDate?: string; retrievedAt?: string }) {
  const retrieved = formatLongDate(retrievedAt) ?? new Date().toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  const updated = formatLongDate(corpusDate);
  return (
    <div className="provenance">
      <Ico name="shield" />
      <span>
        Generated by <b>Federal Regulation Query</b> (regs.bradhinkel.com) from the U.S. eCFR ·
        retrieved {retrieved}
        {updated ? <> · corpus updated as of {updated}</> : null}. This is informational only and not
        legal advice — verify against the official eCFR at{" "}
        <a href="https://www.ecfr.gov" target="_blank" rel="noopener noreferrer">
          ecfr.gov
        </a>{" "}
        before relying on this text.
      </span>
    </div>
  );
}
