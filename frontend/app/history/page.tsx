"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Ico } from "../components/Icons";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";

interface Confidence {
  score: number;
  tier: string;
}

interface HistoryItem {
  id: string;
  query: string;
  plain_english: string;
  legal_language: string;
  citations: { cfr_reference: string }[];
  not_found: boolean;
  strategy_used: string;
  latency_ms: number;
  confidence: Confidence | null;
  created_at: string;
}

const TIER_CLASS: Record<string, string> = {
  high: "conf-high",
  medium: "conf-medium",
  low: "conf-low",
};

export default function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_URL}/history?page=1&page_size=20`)
      .then((r) => r.json())
      .then((data) => {
        setItems(data.items || []);
        setTotal(data.total || 0);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <main className="shell">
      <header className="masthead">
        <div className="brand">
          <Link href="/" className="brand-seal" style={{ textDecoration: "none" }}>
            <Ico name="seal" />
            <span className="wordmark">
              Federal <span className="reg">Regulation</span> Query
            </span>
          </Link>
          <div className="coverage">Query history</div>
        </div>
        <nav className="nav">
          <Link href="/">← Back to search</Link>
        </nav>
      </header>

      <div className="fade-in">
        <div className="trustbar" style={{ marginBottom: 22 }}>
          <h1 className="answer-q">Query history</h1>
          {total > 0 && (
            <div className="trust-chips">
              <span className="trust-chip">
                <b>{total}</b> total queries
              </span>
            </div>
          )}
        </div>

        {loading && <p style={{ color: "var(--text-3)", fontSize: 14 }}>Loading…</p>}

        {!loading && items.length === 0 && (
          <div className="statecard notfound">
            <span className="si">
              <Ico name="empty" style={{ width: 22, height: 22 }} />
            </span>
            <div>
              <div className="st">No queries yet</div>
              <div className="sd">Answered questions will appear here.</div>
            </div>
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {items.map((item) => (
            <div
              key={item.id}
              className="panel"
              style={{ padding: "18px 20px", boxShadow: "none" }}
            >
              <p
                style={{
                  fontFamily: "var(--font-serif)",
                  fontSize: 17,
                  color: "var(--text)",
                  margin: "0 0 8px",
                }}
              >
                {item.query}
              </p>
              {item.not_found ? (
                <p style={{ fontSize: 13, color: "var(--text-3)", fontStyle: "italic", margin: 0 }}>
                  Not found in indexed regulations
                </p>
              ) : (
                <p
                  style={{
                    fontSize: 13.5,
                    color: "var(--text-2)",
                    lineHeight: 1.55,
                    margin: 0,
                    display: "-webkit-box",
                    WebkitLineClamp: 3,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }}
                >
                  {item.plain_english}
                </p>
              )}
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  alignItems: "center",
                  gap: 14,
                  marginTop: 12,
                  fontSize: 11.5,
                  color: "var(--text-3)",
                  fontFamily: "var(--font-mono)",
                }}
              >
                <span>{new Date(item.created_at).toLocaleString()}</span>
                <span>
                  {item.citations.length} citation{item.citations.length !== 1 ? "s" : ""}
                </span>
                <span>{item.latency_ms} ms</span>
                {item.confidence && !item.not_found && (
                  <span
                    className={"trust-chip " + (TIER_CLASS[item.confidence.tier] ?? "")}
                    style={{ padding: "3px 9px", fontSize: 11 }}
                  >
                    {item.confidence.tier} confidence
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
