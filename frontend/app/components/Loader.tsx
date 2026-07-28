"use client";

import { Ico } from "./Icons";

type LoadStatus = "classifying" | "retrieving" | "comparing" | "generating" | "verifying";

interface LoaderProps {
  query: string;
  status: LoadStatus;
  temporal?: boolean;
}

interface Step {
  key: LoadStatus;
  label: string;
  sub: string;
}

const BASE_STEPS: Step[] = [
  { key: "classifying", label: "Classifying your question", sub: "Determining intent and scope" },
  {
    key: "retrieving",
    label: "Searching the Code of Federal Regulations",
    sub: "Retrieving grounded sections across 8 titles",
  },
  {
    key: "comparing",
    label: "Comparing current and prior versions",
    sub: "Diffing the active and archived editions",
  },
  {
    key: "generating",
    label: "Generating grounded answer",
    sub: "Synthesizing three registers with verbatim quotes",
  },
  {
    key: "verifying",
    label: "Verifying grounding",
    sub: "An independent judge is checking each claim against the retrieved text",
  },
];

export default function Loader({ query, status, temporal }: LoaderProps) {
  // The temporal "compare" stage only appears for "what changed?" queries; the
  // "verifying" stage only appears once the grounding judge actually escalates.
  const steps = BASE_STEPS.filter(
    (s) =>
      (s.key !== "comparing" || temporal || status === "comparing") &&
      (s.key !== "verifying" || status === "verifying")
  );
  const activeIdx = Math.max(
    0,
    steps.findIndex((s) => s.key === status)
  );

  return (
    <div className="loader fade-in">
      <div className="loader-head">
        Answering <span className="q">“{query}”</span>
      </div>
      <div className="pipeline">
        {steps.map((s, i) => {
          const state = i < activeIdx ? "done" : i === activeIdx ? "active" : "pending";
          return (
            <div className="pstep" data-state={state} key={s.key}>
              <span className="pdot">
                {state === "done" ? (
                  <Ico name="check" className="check" />
                ) : state === "active" ? (
                  <span className="spin" />
                ) : (
                  i + 1
                )}
              </span>
              <div>
                <div className="plabel">{s.label}</div>
                <div className="psub">{s.sub}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
