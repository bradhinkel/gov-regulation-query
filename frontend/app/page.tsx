"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import QueryForm from "./components/QueryForm";
import ResponsePanel from "./components/ResponsePanel";
import StatusBanner from "./components/StatusBanner";
import PrintButton from "./components/PrintButton";
import PrintableResult from "./components/PrintableResult";
import AboutModal from "./components/AboutModal";
import { Citation } from "./components/CitationList";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";

type Status =
  | "idle"
  | "classifying"
  | "retrieving"
  | "comparing"
  | "generating"
  | "done"
  | "off_topic"
  | "error";

interface Confidence {
  score: number;
  tier: string;
  retrieval_score: number;
  citation_coverage: number;
  verified_citations: string[];
  unverified_citations: string[];
}

interface QueryResult {
  id: string;
  query: string;
  plain_english: string;
  legal_language: string;
  citations: Citation[];
  not_found: boolean;
  strategy_used: string;
  latency_ms: number;
  confidence: Confidence | null;
  temporal?: boolean;
  created_at: string;
}

interface SourceTitle {
  source_id: string;
  title_number?: number;
  agency?: string;
  chunk_count: number;
}

export default function Home() {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string>();
  const [offTopic, setOffTopic] = useState<string>();
  const [result, setResult] = useState<QueryResult | null>(null);
  const [sources, setSources] = useState<SourceTitle[]>([]);
  const [aboutOpen, setAboutOpen] = useState(false);

  useEffect(() => {
    fetch(`${API_URL}/sources`)
      .then((r) => r.json())
      .then((data) => setSources(data.sources || []))
      .catch(() => {});
  }, []);

  const handleQuery = async (
    query: string,
    options: { titleNumber?: number; strategy?: string }
  ) => {
    setStatus("classifying");
    setError(undefined);
    setOffTopic(undefined);
    setResult(null);

    try {
      const response = await fetch(`${API_URL}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          title_number: options.titleNumber || null,
          strategy: options.strategy || null,
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error(`Server error: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        let currentEvent = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const data = JSON.parse(line.slice(6));
            if (currentEvent === "status") {
              setStatus(data.status as Status);
            } else if (currentEvent === "result") {
              setResult(data);
              setStatus("done");
            } else if (currentEvent === "off_topic") {
              setOffTopic(data.message);
              setStatus("off_topic");
            } else if (currentEvent === "error") {
              setError(data.error);
              setStatus("error");
            }
          }
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setStatus("error");
    }
  };

  // Aggregate chunk counts per unique title for the subtitle
  const titleCount = new Set(sources.map((s) => s.title_number).filter(Boolean)).size;
  const totalChunks = sources.reduce((sum, s) => sum + s.chunk_count, 0);

  return (
    <main className="min-h-screen px-4 py-10 max-w-3xl mx-auto space-y-8">
      <header className="space-y-1">
        <div className="flex items-baseline justify-between">
          <h1 className="text-2xl font-bold text-[var(--accent)] tracking-wide">
            Federal Regulation Query
          </h1>
          <div className="flex items-center gap-4">
            <button
              onClick={() => setAboutOpen(true)}
              className="text-sm text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
            >
              About
            </button>
            <Link
              href="/history"
              className="text-sm text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
            >
              Query history →
            </Link>
          </div>
        </div>
        <p className="text-sm text-[var(--muted)]">
          {titleCount > 0
            ? `${titleCount} CFR title${titleCount !== 1 ? "s" : ""} indexed — ${totalChunks.toLocaleString()} sections`
            : "Search the Code of Federal Regulations"}
        </p>
      </header>

      <QueryForm
        onSubmit={handleQuery}
        isLoading={
          status === "classifying" ||
          status === "retrieving" ||
          status === "comparing" ||
          status === "generating"
        }
        sources={sources}
      />

      <StatusBanner status={status} error={error} offTopic={offTopic} />

      {result && status === "done" && (
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-[var(--muted)] truncate">
              &ldquo;{result.query}&rdquo;
            </p>
            <div className="flex items-center gap-3 flex-shrink-0">
              {result.temporal && (
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium
                  border border-purple-800 bg-purple-900/40 text-purple-300">
                  Change comparison
                </span>
              )}
              {result.confidence && !result.not_found && (
                <ConfidenceBadge confidence={result.confidence} />
              )}
              {!result.not_found && <PrintButton />}
            </div>
          </div>
          <ResponsePanel
            plainEnglish={result.plain_english}
            legalLanguage={result.legal_language}
            citations={result.citations}
            notFound={result.not_found}
            strategyUsed={result.strategy_used}
            latencyMs={result.latency_ms}
          />
          {!result.not_found && (
            <PrintableResult
              query={result.query}
              plainEnglish={result.plain_english}
              legalLanguage={result.legal_language}
              citations={result.citations}
              createdAt={result.created_at}
            />
          )}
        </div>
      )}

      <AboutModal open={aboutOpen} onClose={() => setAboutOpen(false)} />
    </main>
  );
}

function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  const tierColors: Record<string, string> = {
    high:      "bg-green-900/40 text-green-400 border-green-800",
    medium:    "bg-yellow-900/40 text-yellow-400 border-yellow-800",
    low:       "bg-red-900/40 text-red-400 border-red-800",
    not_found: "bg-gray-800 text-gray-500 border-gray-700",
  };
  const color = tierColors[confidence.tier] ?? tierColors.low;
  const pct = Math.round(confidence.score * 100);

  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full border font-medium ${color}`}
      title={`Retrieval: ${Math.round(confidence.retrieval_score * 100)}%  Citation coverage: ${Math.round(confidence.citation_coverage * 100)}%`}
    >
      {confidence.tier === "not_found" ? "not found" : `${confidence.tier} confidence · ${pct}%`}
    </span>
  );
}
