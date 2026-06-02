"use client";

type Status =
  | "idle"
  | "classifying"
  | "retrieving"
  | "generating"
  | "done"
  | "off_topic"
  | "error";

interface StatusBannerProps {
  status: Status;
  error?: string;
  offTopic?: string;
}

export default function StatusBanner({ status, error, offTopic }: StatusBannerProps) {
  if (status === "idle" || status === "done") return null;

  if (status === "error") {
    return (
      <div className="rounded-lg border border-red-800 bg-red-950/30 px-4 py-3 text-sm text-red-400">
        {error || "An error occurred. Please try again."}
      </div>
    );
  }

  if (status === "off_topic") {
    return (
      <div className="rounded-lg border border-amber-800 bg-amber-950/30 px-4 py-3 text-sm text-amber-300">
        {offTopic ||
          "This system answers questions about U.S. federal regulations. Please rephrase your question as a regulatory inquiry."}
      </div>
    );
  }

  const messages: Record<string, string> = {
    classifying: "Checking your question…",
    retrieving: "Searching the Code of Federal Regulations…",
    generating: "Generating plain English and legal language responses…",
  };

  return (
    <div className="flex items-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--muted)]">
      <span className="inline-block w-4 h-4 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
      {messages[status]}
    </div>
  );
}
