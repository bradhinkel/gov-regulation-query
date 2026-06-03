"use client";

/**
 * PrintButton — generic, dependency-free "Print / Save as PDF" trigger.
 *
 * Reusable across projects. Pairs with the print conventions in globals.css:
 *   - elements with class `no-print`  are hidden when printing
 *   - a single container with class `print-only` is the *only* thing printed
 * Drop this component in, add a `.print-only` printable view, and the browser's
 * native "Save as PDF" produces a clean document. No server/PDF dependency.
 */
interface PrintButtonProps {
  label?: string;
  className?: string;
}

export default function PrintButton({
  label = "Print / Save as PDF",
  className = "",
}: PrintButtonProps) {
  return (
    <button
      type="button"
      onClick={() => window.print()}
      className={
        "no-print inline-flex items-center gap-1.5 rounded-md border border-[var(--border)] " +
        "bg-[var(--surface-2)] px-3 py-1.5 text-xs text-[var(--muted)] " +
        "hover:text-[var(--foreground)] hover:border-[var(--accent)] transition-colors " +
        className
      }
      title="Open the print dialog — choose 'Save as PDF' to export"
    >
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <polyline points="6 9 6 2 18 2 18 9" />
        <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" />
        <rect x="6" y="14" width="12" height="8" />
      </svg>
      {label}
    </button>
  );
}
