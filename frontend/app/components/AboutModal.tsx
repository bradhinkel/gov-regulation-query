"use client";

import { useEffect } from "react";
import { Ico } from "./Icons";

interface AboutModalProps {
  onClose: () => void;
}

const LINKS = [
  { label: "Built by Brad Hinkel", href: "https://bradhinkel.com", sub: "bradhinkel.com" },
  { label: "Source on GitHub", href: "https://github.com/bradhinkel/gov-regulation-query", sub: "repository" },
  { label: "Built with Claude Code", href: "https://claude.com/claude-code", sub: "claude.com/claude-code" },
];

export default function AboutModal({ onClose }: AboutModalProps) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);

  return (
    <div className="overlay no-print" onClick={onClose} role="dialog" aria-modal="true" aria-label="About this tool">
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>About this tool</h2>
          <button className="modal-x" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <div className="modal-body">
          <p className="modal-summary">
            Government Regulation Query is a retrieval-augmented system over the U.S. Code of Federal
            Regulations. Ask a plain-English question and get three grounded answers — a plain-English
            explanation, a formal legal-language synthesis with verbatim quotes, and precise CFR
            citations — each tied to the current eCFR edition.
          </p>
          <div className="modal-stats">
            <div className="modal-stat">
              <div className="v">8</div>
              <div className="k">CFR titles indexed</div>
            </div>
            <div className="modal-stat">
              <div className="v">265K</div>
              <div className="k">sections grounded</div>
            </div>
            <div className="modal-stat">
              <div className="v">3</div>
              <div className="k">answer registers</div>
            </div>
          </div>
          <div className="modal-links">
            {LINKS.map((l) => (
              <a
                key={l.href}
                className="modal-link"
                href={l.href}
                target="_blank"
                rel="noopener noreferrer"
              >
                <span className="ml-l">{l.label}</span>
                <span className="ml-r">
                  {l.sub} <Ico name="ext" style={{ width: 13, height: 13 }} />
                </span>
              </a>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
