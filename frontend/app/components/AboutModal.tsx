"use client";

interface AboutModalProps {
  open: boolean;
  onClose: () => void;
}

const LINKS = [
  { label: "Built by Brad Hinkel", href: "https://bradhinkel.com", sub: "bradhinkel.com" },
  { label: "Source on GitHub", href: "https://github.com/bradhinkel/gov-regulation-query", sub: "repository" },
  { label: "Built with Claude Code", href: "https://claude.com/claude-code", sub: "claude.com/claude-code" },
];

export default function AboutModal({ open, onClose }: AboutModalProps) {
  if (!open) return null;
  return (
    <div
      onClick={onClose}
      className="no-print fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="About this project"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6 space-y-4 shadow-xl"
      >
        <div className="flex items-start justify-between">
          <h2 className="text-lg font-bold text-[var(--accent)]">About</h2>
          <button
            onClick={onClose}
            className="text-[var(--muted)] hover:text-[var(--foreground)] text-xl leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <p className="text-sm leading-relaxed text-[var(--foreground)]">
          Government Regulation Query is a retrieval-augmented generation system over
          the U.S. Code of Federal Regulations. Ask a plain-English question and get
          three grounded answers — a plain-English explanation, a formal legal-language
          synthesis with verbatim quotes, and precise CFR citations — each tied to the
          current eCFR edition. It spans 8 major CFR titles (~265,000 sections), shows a
          confidence signal on every answer, and uses a versioned-replacement pipeline
          to keep citations current.
        </p>

        <div className="flex flex-col gap-2 pt-1">
          {LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-between rounded-md border border-[var(--border)]
                bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--foreground)]
                hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
            >
              <span>{l.label}</span>
              <span className="text-xs text-[var(--muted)]">{l.sub} ↗</span>
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}
