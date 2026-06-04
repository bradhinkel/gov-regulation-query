// Shared types for the Federal Regulation Query frontend.

export interface Citation {
  cfr_reference: string;
  title_number?: number;
  part_number?: string;
  section_number?: string;
  section_heading?: string;
  agency?: string;
  source_id: string;
  citation_string?: string;
  effective_date?: string; // eCFR edition date ("current as of")
}

export interface Confidence {
  score: number; // 0..1 from the API
  tier: string; // "high" | "medium" | "low" | "not_found"
  retrieval_score: number;
  citation_coverage: number;
  verified_citations?: string[];
  unverified_citations?: string[];
}

export interface QueryResult {
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

export interface SourceTitle {
  source_id: string;
  title_number?: number;
  agency?: string;
  chunk_count: number;
  latest_date?: string;
}

// ---- parsed answer blocks (the design's render model) ----
export type Block =
  | { t: "h2" | "h3" | "p"; html: string; lead?: boolean }
  | { t: "ul"; items: { html: string; cite?: string }[] }
  | { t: "quote"; text: string; cite?: string };
