"use client";

interface SourceTitle {
  source_id: string;
  title_number?: number;
  agency?: string;
  chunk_count: number;
}

interface QueryFormProps {
  onSubmit: (query: string, options: { titleNumber?: number; strategy?: string }) => void;
  isLoading: boolean;
  sources: SourceTitle[];
}

export default function QueryForm({ onSubmit, isLoading, sources }: QueryFormProps) {
  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = e.currentTarget;
    const query = (form.elements.namedItem("query") as HTMLInputElement).value.trim();
    const titleVal = (form.elements.namedItem("titleNumber") as HTMLSelectElement)?.value;
    const titleNumber = titleVal ? parseInt(titleVal) : undefined;
    const strategy = (form.elements.namedItem("strategy") as HTMLSelectElement).value || undefined;
    if (query) onSubmit(query, { titleNumber, strategy });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <textarea
        name="query"
        rows={3}
        placeholder="Ask a regulatory question… e.g. What are the labeling requirements for organic produce? What does OSHA require for fall protection?"
        className="w-full rounded-lg px-4 py-3 text-base resize-none
          bg-[var(--surface-2)] border border-[var(--border)]
          text-[var(--foreground)] placeholder-[var(--muted)]
          focus:outline-none focus:border-[var(--accent)]"
        disabled={isLoading}
      />

      <div className="flex flex-wrap gap-3 items-center">
        {sources.length > 0 && (
          <select
            name="titleNumber"
            className="rounded px-3 py-2 text-sm bg-[var(--surface-2)] border border-[var(--border)]
              text-[var(--foreground)] focus:outline-none focus:border-[var(--accent)]"
          >
            <option value="">All titles</option>
            {sources.map((s) => (
              <option key={s.source_id} value={s.title_number ?? ""}>
                {s.title_number ? `Title ${s.title_number}` : s.source_id}
                {s.agency ? ` — ${s.agency}` : ""}
              </option>
            ))}
          </select>
        )}

        <select
          name="strategy"
          className="rounded px-3 py-2 text-sm bg-[var(--surface-2)] border border-[var(--border)]
            text-[var(--foreground)] focus:outline-none focus:border-[var(--accent)]"
        >
          <option value="sequential">Sequential (recommended)</option>
          <option value="single">Single call</option>
        </select>

        <button
          type="submit"
          disabled={isLoading}
          className="ml-auto px-6 py-2 rounded-lg font-semibold text-sm
            bg-[var(--accent)] text-white hover:bg-[var(--accent-dark)]
            disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {isLoading ? "Searching regulations…" : "Search"}
        </button>
      </div>
    </form>
  );
}
