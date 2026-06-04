"use client";

import { useState } from "react";
import { CFR_TITLES, titleLabel } from "../lib/cfr";
import { Ico } from "./Icons";
import Field from "./Field";

interface HomeViewProps {
  onSearch: (query: string, options: { titleNumber: number | null; strategy: string }) => void;
}

const EXAMPLES = [
  "What are the labeling requirements for organic blueberries?",
  "Does 21 CFR require allergen declarations on packaged foods?",
  "What changed in the definitions of controlled substances?",
  "What are OSHA's fall-protection rules for construction?",
];

export default function HomeView({ onSearch }: HomeViewProps) {
  const [q, setQ] = useState("");
  const [titleFilter, setTitleFilter] = useState<string>("");
  const [strategy, setStrategy] = useState<string>("sequential");

  const titleOptions = [
    { value: "", label: "All titles" },
    ...CFR_TITLES.map((t) => ({ value: String(t.num), label: titleLabel(t.num) })),
  ];

  const submit = (query: string) => {
    if (!query.trim()) return;
    onSearch(query.trim(), {
      titleNumber: titleFilter ? parseInt(titleFilter, 10) : null,
      strategy,
    });
  };

  return (
    <div className="fade-in">
      <div className="eyebrow" style={{ marginBottom: 16 }}>
        <span className="tick">
          <Ico name="shieldcheck" style={{ width: 14, height: 14 }} />
        </span>
        Retrieval-augmented · grounded in the actual CFR text
      </div>

      <div className="composer">
        <div className="composer-head">
          <textarea
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Ask a regulatory question…  e.g. What are the labeling requirements for organic produce? What does 21 CFR require for food additives?"
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(q);
            }}
          />
        </div>
        <div className="composer-bar">
          <Field label="Filter" value={titleFilter} options={titleOptions} onChange={setTitleFilter} />
          <Field
            label="Strategy"
            value={strategy}
            options={[
              { value: "sequential", label: "Sequential (recommended)" },
              { value: "single", label: "Single call" },
            ]}
            onChange={setStrategy}
          />
          <span className="spacer" />
          <button className="btn-search" onClick={() => submit(q)} disabled={!q.trim()}>
            <Ico name="search" />
            Search regulations
          </button>
        </div>
      </div>

      <div className="composer-note">
        <Ico name="shield" />
        <span>
          Informational only — not legal advice. Every answer is grounded in the current eCFR; verify
          against the official text at{" "}
          <a href="https://www.ecfr.gov" target="_blank" rel="noopener noreferrer">
            ecfr.gov
          </a>{" "}
          before relying on it.
        </span>
      </div>

      <div className="examples">
        <div className="examples-label">Try one of these</div>
        <div className="chip-row">
          {EXAMPLES.map((ex, i) => (
            <button className="chip" key={i} onClick={() => submit(ex)}>
              <span className="q">?</span>
              {ex}
            </button>
          ))}
        </div>
      </div>

      <div className="howto">
        <div className="howto-cell">
          <div className="howto-step">STEP 01</div>
          <div className="howto-title">Ask in plain English</div>
          <div className="howto-desc">
            No legalese required. Filter to a specific CFR title or search all{" "}
            <span className="reg">8 indexed titles</span> at once.
          </div>
        </div>
        <div className="howto-cell">
          <div className="howto-step">STEP 02</div>
          <div className="howto-title">We retrieve the real text</div>
          <div className="howto-desc">
            The system pulls grounded sections from the{" "}
            <span className="reg">current eCFR edition</span> — never the model&apos;s memory.
          </div>
        </div>
        <div className="howto-cell">
          <div className="howto-step">STEP 03</div>
          <div className="howto-title">Three grounded answers</div>
          <div className="howto-desc">Every response, verifiable against the source.</div>
          <div className="register-pills">
            <span className="register-pill">Plain English</span>
            <span className="register-pill">Legal Language</span>
            <span className="register-pill">CFR Citations</span>
          </div>
        </div>
      </div>

      <div className="titles-strip">
        <div className="examples-label">Coverage — 8 major titles</div>
        <div className="title-tags">
          {CFR_TITLES.map((t) => (
            <span className="title-tag" key={t.num}>
              <span className="num">{t.num}</span>
              {t.name}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
