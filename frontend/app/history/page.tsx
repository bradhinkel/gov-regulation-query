"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";

interface HistoryItem {
  id: string;
  query: string;
  plain_english: string;
  legal_language: string;
  citations: { cfr_reference: string }[];
  not_found: boolean;
  strategy_used: string;
  latency_ms: number;
  created_at: string;
}

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
    <main className="min-h-screen px-4 py-10 max-w-3xl mx-auto space-y-6">
      <header className="flex items-baseline justify-between">
        <h1 className="text-2xl font-bold text-[var(--accent)]">Query History</h1>
        <Link
          href="/"
          className="text-sm text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
        >
          ← Back
        </Link>
      </header>

      {loading && (
        <p className="text-[var(--muted)] text-sm">Loading…</p>
      )}

      {!loading && items.length === 0 && (
        <p className="text-[var(--muted)] text-sm italic">No queries yet.</p>
      )}

      {total > 0 && (
        <p className="text-xs text-[var(--muted)]">{total} total queries</p>
      )}

      <div className="space-y-4">
        {items.map((item) => (
          <div
            key={item.id}
            className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 space-y-2"
          >
            <p className="text-sm font-medium text-[var(--foreground)]">
              &ldquo;{item.query}&rdquo;
            </p>
            {item.not_found ? (
              <p className="text-xs text-[var(--muted)] italic">Not found</p>
            ) : (
              <p className="text-xs text-[var(--foreground)] line-clamp-3 leading-relaxed">
                {item.plain_english}
              </p>
            )}
            <div className="flex items-center gap-3 text-xs text-[var(--muted)]">
              <span>{new Date(item.created_at).toLocaleString()}</span>
              <span>{item.citations.length} citation{item.citations.length !== 1 ? "s" : ""}</span>
              <span>{item.latency_ms}ms</span>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
