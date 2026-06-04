// Icons + small shared UI primitives for Federal Regulation Query
const { useState, useEffect, useRef } = React;

// ---- icon set (stroke, inherits currentColor) ----
const ICONS = {
  search: 'M11 4a7 7 0 1 0 4.2 12.6L20 21M11 4a7 7 0 0 1 5 11.9',
  chevron: 'M4 7l4 4 4-4',
  seal: null, // drawn separately
  scale: 'M12 3v18M5 21h14M7 7h10M7 7 4 14a3 3 0 0 0 6 0L7 7Zm10 0-3 7a3 3 0 0 0 6 0l-3-7ZM12 3 7 7m5-4 5 4',
  book: 'M4 5.5A1.5 1.5 0 0 1 5.5 4H19v15H6a2 2 0 0 0-2 2V5.5ZM6 19a2 2 0 0 0-2 2',
  list: 'M8 6h12M8 12h12M8 18h12M3.5 6h.01M3.5 12h.01M3.5 18h.01',
  check: 'M4 12l5 5L20 6',
  shield: 'M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3Z',
  shieldcheck: 'M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3Zm-3 8 2 2 4-4',
  clock: 'M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
  printer: 'M6 9V3h12v6M6 18H4v-7h16v7h-2M8 14h8v7H8v-7Z',
  ext: 'M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5',
  edit: 'M4 20h4L19 9a2 2 0 0 0-3-3L5 17v3ZM14 7l3 3',
  spark: 'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z',
  alert: 'M12 9v4m0 4h.01M10.3 4.3 2.5 18a2 2 0 0 0 1.7 3h15.6a2 2 0 0 0 1.7-3L13.7 4.3a2 2 0 0 0-3.4 0Z',
  empty: 'M21 21l-5-5m2-5a7 7 0 1 1-14 0 7 7 0 0 1 14 0Zm-7-3v3m0 3h.01',
  arrow: 'M5 12h14M13 6l6 6-6 6',
};

function Ico({ name, className, style }) {
  if (name === 'seal') return <Seal className={className} style={style} />;
  const d = ICONS[name];
  return (
    <svg className={className} style={style} viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  );
}

// Federal "seal" mark — concentric ring with a column motif (authority, not a real gov seal)
function Seal({ className, style }) {
  return (
    <svg className={className} style={style} viewBox="0 0 32 32" fill="none">
      <circle cx="16" cy="16" r="14.2" stroke="var(--accent)" strokeWidth="1.4" />
      <circle cx="16" cy="16" r="11" stroke="var(--accent)" strokeWidth="0.8" opacity="0.5" />
      <path d="M16 7.5 9.5 11h13L16 7.5Z" fill="var(--accent)" />
      <rect x="10.4" y="12" width="1.7" height="7" rx="0.4" fill="var(--accent)" />
      <rect x="15.15" y="12" width="1.7" height="7" rx="0.4" fill="var(--accent)" />
      <rect x="19.9" y="12" width="1.7" height="7" rx="0.4" fill="var(--accent)" />
      <rect x="8.5" y="19.4" width="15" height="1.8" rx="0.6" fill="var(--accent)" />
    </svg>
  );
}

// dropdown field
function Field({ label, value, options, onChange }) {
  return (
    <div className="field-wrap" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      {label && <span className="field-label">{label}</span>}
      <span className="field">
        <select value={value} onChange={(e) => onChange && onChange(e.target.value)}>
          {options.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
        <Ico name="chevron" />
      </span>
    </div>
  );
}

Object.assign(window, { Ico, Seal, Field, useState, useEffect, useRef });
