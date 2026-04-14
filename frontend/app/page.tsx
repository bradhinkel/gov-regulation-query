"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import QueryForm from "./components/QueryForm";
import ResponsePanel from "./components/ResponsePanel";
import StatusBanner from "./components/StatusBanner";
import { Citation } from "./components/CitationList";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";

type Status = "idle" | "retrieving" | "generating" | "done" | "error";

interface QueryResult {
  id: string;
  query: string;
  plain_english: string;
  legal_language: string;
  citations: Citation[];
  not_found: boolean;
  strategy_used: string;
  latency_ms: number;
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
  const [result, setResult] = useState<QueryResult | null>(null);
  const [sources, setSources] = useState<SourceTitle[]>([]);

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
    setStatus("retrieving");
    setError(undefined);
    setResult(null);

    try {
      const response = await fetch(`${API_URL}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          title_number: options.titleNumber || null,
          strategy: options.strategy || null,
          top_k: 6,
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
              setStatus(data.status === "generating" ? "generating" : "retrieving");
            } else if (currentEvent === "result") {
              setResult(data);
              setStatus("done");
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

  const totalChunks = sources.reduce((sum, s) => sum + s.chunk_count, 0);

  return (
    <main className="min-h-screen px-4 py-10 max-w-3xl mx-auto space-y-8">
      <header className="space-y-1">
        <div className="flex items-baseline justify-between">
          <h1 className="text-2xl font-bold text-[var(--accent)] tracking-wide">
            Federal Regulation Query
          </h1>
          <Link
            href="/history"
            className="text-sm text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
          >
            Query history →
          </Link>
        </div>
        <p className="text-sm text-[var(--muted)]">
          {sources.length > 0
            ? `${sources.length} CFR title${sources.length !== 1 ? "s" : ""} indexed — ${totalChunks.toLocaleString()} sections`
            : "Search the Code of Federal Regulations"}
        </p>
      </header>

      <QueryForm
        onSubmit={handleQuery}
        isLoading={status === "retrieving" || status === "generating"}
        sources={sources}
      />

      <StatusBanner status={status} error={error} />

      {result && status === "done" && (
        <div className="space-y-2">
          <p className="text-xs text-[var(--muted)]">
            &ldquo;{result.query}&rdquo;
          </p>
          <ResponsePanel
            plainEnglish={result.plain_english}
            legalLanguage={result.legal_language}
            citations={result.citations}
            notFound={result.not_found}
            strategyUsed={result.strategy_used}
            latencyMs={result.latency_ms}
          />
        </div>
      )}
    </main>
  );
}
