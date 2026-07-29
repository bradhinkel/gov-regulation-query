"use client";

import { useEffect, useRef, useState } from "react";
import type { QueryResult, SourceTitle } from "./lib/types";
import { corpusUpdatedDate } from "./lib/cfr";
import Masthead from "./components/Masthead";
import HomeView from "./components/HomeView";
import Loader from "./components/Loader";
import ResultView from "./components/ResultView";
import { CompactQuery, OffTopic, NotFound, ErrorState } from "./components/StateCard";
import AboutModal from "./components/AboutModal";
import PrintableResult from "./components/PrintableResult";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";

type Status =
  | "idle"
  | "classifying"
  | "retrieving"
  | "comparing"
  | "scanning"
  | "generating"
  | "verifying"
  | "done"
  | "off_topic"
  | "error";

const LOADING_STATUSES: Status[] = [
  "classifying",
  "retrieving",
  "comparing",
  "scanning",
  "generating",
  "verifying",
];

export default function Home() {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string>();
  const [offTopic, setOffTopic] = useState<string>();
  const [result, setResult] = useState<QueryResult | null>(null);
  const [sources, setSources] = useState<SourceTitle[]>([]);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [temporal, setTemporal] = useState(false);

  // Remember the last submitted query + filter so the compact bar / states can echo it
  const [lastQuery, setLastQuery] = useState("");
  const [titleFilter, setTitleFilter] = useState<number | null>(null);
  const lastStrategy = useRef<string>("sequential");

  useEffect(() => {
    fetch(`${API_URL}/sources`)
      .then((r) => r.json())
      .then((data) => setSources(data.sources || []))
      .catch(() => {});
  }, []);

  const runQuery = async (
    query: string,
    options: { titleNumber: number | null; strategy: string }
  ) => {
    setLastQuery(query);
    setTitleFilter(options.titleNumber);
    lastStrategy.current = options.strategy;
    setStatus("classifying");
    setError(undefined);
    setOffTopic(undefined);
    setResult(null);
    setTemporal(false);
    window.scrollTo({ top: 0 });

    try {
      const response = await fetch(`${API_URL}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          title_number: options.titleNumber,
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
              const s = data.status as Status;
              if (s === "comparing") setTemporal(true);
              setStatus(s);
            } else if (currentEvent === "result") {
              setResult(data as QueryResult);
              setTemporal(Boolean((data as QueryResult).temporal));
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

  const goHome = () => {
    setStatus("idle");
    setResult(null);
    setError(undefined);
    setOffTopic(undefined);
    window.scrollTo({ top: 0 });
  };

  const refilter = (titleNumber: number | null) => {
    if (!lastQuery) return;
    runQuery(lastQuery, { titleNumber, strategy: lastStrategy.current });
  };

  // Masthead coverage figures (live from /sources, with sensible fallbacks)
  const titleCount =
    new Set(sources.map((s) => s.title_number).filter((n) => n != null)).size || 8;
  const sectionCount = sources.reduce((sum, s) => sum + s.chunk_count, 0) || 265641;
  const corpusDate = corpusUpdatedDate(sources);

  let body: React.ReactNode;
  if (LOADING_STATUSES.includes(status)) {
    body = (
      <Loader
        query={lastQuery}
        status={
          status as
            | "classifying"
            | "retrieving"
            | "comparing"
            | "scanning"
            | "generating"
            | "verifying"
        }
        temporal={temporal}
      />
    );
  } else if (status === "off_topic") {
    body = (
      <>
        <CompactQuery query={lastQuery} onNew={goHome} />
        <OffTopic message={offTopic} />
      </>
    );
  } else if (status === "error") {
    body = (
      <>
        <CompactQuery query={lastQuery} onNew={goHome} />
        <ErrorState message={error} />
      </>
    );
  } else if (status === "done" && result) {
    if (result.not_found) {
      body = (
        <>
          <CompactQuery query={result.query} onNew={goHome} />
          <NotFound />
        </>
      );
    } else {
      body = (
        <>
          <ResultView
            data={result}
            corpusDate={corpusDate}
            titleFilter={titleFilter}
            onNew={goHome}
            onRefilter={refilter}
          />
          <PrintableResult
            query={result.query}
            plainEnglish={result.plain_english}
            legalLanguage={result.legal_language}
            citations={result.citations}
            createdAt={result.created_at}
            corpusDate={corpusDate}
          />
        </>
      );
    }
  } else {
    body = <HomeView onSearch={runQuery} />;
  }

  return (
    <main className="shell">
      <Masthead
        titleCount={titleCount}
        sectionCount={sectionCount}
        onAbout={() => setAboutOpen(true)}
        onHome={goHome}
      />
      {body}
      {aboutOpen && <AboutModal onClose={() => setAboutOpen(false)} />}
    </main>
  );
}
