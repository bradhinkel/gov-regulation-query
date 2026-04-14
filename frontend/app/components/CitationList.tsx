"use client";

export interface Citation {
  cfr_reference: string;
  title_number?: number;
  part_number?: string;
  section_number?: string;
  section_heading?: string;
  agency?: string;
  source_id: string;
  citation_string?: string;
}

interface CitationListProps {
  citations: Citation[];
}

export default function CitationList({ citations }: CitationListProps) {
  if (!citations || citations.length === 0) {
    return (
      <p className="text-[var(--muted)] italic text-sm">No citations available.</p>
    );
  }

  return (
    <ol className="space-y-4">
      {citations.map((c, i) => (
        <li key={i} className="flex gap-3 text-sm">
          <span className="flex-shrink-0 w-6 h-6 rounded-full bg-[var(--accent)] text-white
            flex items-center justify-center text-xs font-bold">
            {i + 1}
          </span>
          <div className="flex-1">
            <p className="font-semibold text-[var(--foreground)]">
              {c.cfr_reference}
            </p>
            {c.section_heading && (
              <p className="text-[var(--muted)]">{c.section_heading}</p>
            )}
            {c.agency && (
              <p className="text-[var(--accent)] text-xs mt-0.5">{c.agency}</p>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
