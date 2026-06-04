"use client";

import Link from "next/link";
import { Ico } from "./Icons";

interface MastheadProps {
  titleCount: number;
  sectionCount: number;
  onAbout: () => void;
  onHome: () => void;
}

export default function Masthead({ titleCount, sectionCount, onAbout, onHome }: MastheadProps) {
  return (
    <header className="masthead">
      <div className="brand">
        <div className="brand-seal" onClick={onHome} style={{ cursor: "pointer" }}>
          <Ico name="seal" />
          <span className="wordmark">
            Federal <span className="reg">Regulation</span> Query
          </span>
        </div>
        <div className="coverage">
          <b>{titleCount}</b> CFR titles indexed · <b>{sectionCount.toLocaleString()}</b> sections grounded
        </div>
      </div>
      <nav className="nav">
        <button onClick={onAbout}>About</button>
        <Link href="/history">Query history&nbsp;→</Link>
      </nav>
    </header>
  );
}
