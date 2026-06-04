"use client";

import { Ico } from "./Icons";

export interface FieldOption {
  value: string;
  label: string;
}

interface FieldProps {
  label?: string;
  value: string;
  options: FieldOption[];
  onChange?: (value: string) => void;
  disabled?: boolean;
  "aria-label"?: string;
}

/** Styled <select> dropdown primitive with a custom chevron. */
export default function Field({
  label,
  value,
  options,
  onChange,
  disabled,
  "aria-label": ariaLabel,
}: FieldProps) {
  return (
    <span className="field-wrap" style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      {label && <span className="field-label">{label}</span>}
      <span className="field">
        <select
          value={value}
          disabled={disabled}
          aria-label={ariaLabel || label}
          onChange={(e) => onChange?.(e.target.value)}
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <Ico name="chevron" />
      </span>
    </span>
  );
}
