"use client";

import { useState } from "react";
import CitationList, { Citation } from "./CitationList";

type Tab = "plain" | "legal" | "sources";

interface ResponsePanelProps {
  plainEnglish: string;
  legalLanguage: string;
  citations: Citation[];
  notFound: boolean;
  strategyUsed: string;
  latencyMs: number;
}

export default function ResponsePanel({
  plainEnglish,
  legalLanguage,
  citations,
  notFound,
  strategyUsed,
  latencyMs,
}: ResponsePanelProps) {
  const [activeTab, setActiveTab] = useState<Tab>("plain");

  if (notFound) {
    return (
      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6 text-center">
        <p className="text-[var(--muted)] italic text-sm">
          No relevant regulations were found for this query. Try rephrasing,
          or this topic may not be in the indexed titles.
        </p>
      </div>
    );
  }

  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: "plain", label: "Plain English" },
    { id: "legal", label: "Legal Language" },
    { id: "sources", label: "CFR Citations", count: citations.length },
  ];

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] overflow-hidden">
      {/* Tab bar */}
      <div className="flex border-b border-[var(--border)] bg-[var(--surface-2)]">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-5 py-3 text-sm font-medium transition-colors
              ${activeTab === tab.id
                ? "text-[var(--accent)] border-b-2 border-[var(--accent)] -mb-px"
                : "text-[var(--muted)] hover:text-[var(--foreground)]"
              }`}
          >
            {tab.label}
            {tab.count !== undefined && (
              <span className="ml-1.5 px-1.5 py-0.5 rounded-full text-xs bg-[var(--surface)] text-[var(--muted)]">
                {tab.count}
              </span>
            )}
          </button>
        ))}
        <div className="ml-auto flex items-center pr-4 gap-3 text-xs text-[var(--muted)]">
          <span>{strategyUsed}</span>
          <span>{latencyMs}ms</span>
        </div>
      </div>

      {/* Content */}
      <div className="p-6">
        {activeTab === "plain" && (
          <div className="text-[var(--foreground)] leading-relaxed whitespace-pre-wrap text-sm">
            {plainEnglish}
          </div>
        )}

        {activeTab === "legal" && (
          <div className="text-[var(--foreground)] leading-relaxed whitespace-pre-wrap text-sm font-mono">
            {legalLanguage}
          </div>
        )}

        {activeTab === "sources" && (
          <CitationList citations={citations} />
        )}
      </div>
    </div>
  );
}
