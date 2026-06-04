"use client";

import { Ico } from "./Icons";

/** Echoed (greyed) query bar shown above off-topic / not-found / error states. */
export function CompactQuery({ query, onNew }: { query: string; onNew: () => void }) {
  return (
    <div className="searchbar" style={{ marginBottom: 22 }}>
      <Ico name="search" className="icon" style={{ width: 18, height: 18 }} />
      <span className="q-text" style={{ color: "var(--text-3)" }}>
        {query}
      </span>
      <button className="btn-edit" onClick={onNew}>
        New search
      </button>
    </div>
  );
}

export function OffTopic({ message }: { message?: string }) {
  return (
    <div className="statecard offtopic fade-in">
      <span className="si">
        <Ico name="alert" style={{ width: 20, height: 20 }} />
      </span>
      <div>
        <div className="st">Outside the Code of Federal Regulations</div>
        <div className="sd">
          {message ||
            "This system answers questions about U.S. federal regulations only. Try rephrasing as a regulatory question — for example, “What does the FDA require on packaged food labels?”"}
        </div>
      </div>
    </div>
  );
}

export function NotFound() {
  return (
    <div className="statecard notfound fade-in">
      <span className="si">
        <Ico name="empty" style={{ width: 22, height: 22 }} />
      </span>
      <div>
        <div className="st">No grounded sections found</div>
        <div className="sd">
          We searched all 8 indexed titles and found no regulatory text that directly answers this.
          Rather than guess, the system declines — narrow the scope or try a related term.
        </div>
      </div>
    </div>
  );
}

export function ErrorState({ message }: { message?: string }) {
  return (
    <div className="statecard error fade-in">
      <span className="si">
        <Ico name="alert" style={{ width: 20, height: 20 }} />
      </span>
      <div>
        <div className="st">Something went wrong</div>
        <div className="sd">{message || "An error occurred. Please try again."}</div>
      </div>
    </div>
  );
}
