"use client";

const PHASES = [
  { key: "phase1", label: "Phase 1 — Marengo + Pegasus + Audio" },
  { key: "phase2", label: "Phase 2 — Boundary Scoring" },
  { key: "phase3", label: "Phase 3 — Top-K Selection" },
  { key: "complete", label: "Complete" },
];

interface Props {
  status: string;
  progress: number;
}

export default function ProgressBar({ status, progress }: Props) {
  const getPhaseProgress = (phase: string) => {
    const order = ["pending", "processing", "phase1", "phase2", "phase3", "complete"];
    const current = order.indexOf(status);
    const phaseIdx = order.indexOf(phase);
    if (current > phaseIdx) return 100;
    if (current === phaseIdx) return progress;
    return 0;
  };

  if (status === "complete") return null;

  return (
    <div className="card space-y-3">
      <div className="text-xs text-slate-400 font-medium">Processing Pipeline</div>
      {PHASES.slice(0, 3).map((p) => {
        const pct = getPhaseProgress(p.key);
        return (
          <div key={p.key} className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className={pct > 0 ? "text-slate-300" : "text-slate-600"}>{p.label}</span>
              <span className={pct === 100 ? "text-emerald-400" : pct > 0 ? "text-teal-400" : "text-slate-600"}>
                {pct === 100 ? "done" : pct > 0 ? `${pct}%` : "—"}
              </span>
            </div>
            <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  pct === 100 ? "bg-emerald-500" : "bg-teal-500"
                }`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
