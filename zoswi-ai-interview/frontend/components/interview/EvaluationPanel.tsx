"use client";

import type { EvaluationSignals } from "../../lib/types";

type EvaluationPanelProps = {
  signals: EvaluationSignals | null;
};

function Score({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3.5">
      <p className="text-[11px] uppercase tracking-[0.14em] text-slate-400">{label}</p>
      <div className="mt-2 flex items-end justify-between gap-2">
        <p className="text-xl font-semibold text-slate-100">{value.toFixed(1)} / 10</p>
        <div className="h-1.5 w-16 overflow-hidden rounded-full bg-white/10">
          <div
            className="h-full rounded-full bg-gradient-to-r from-cyan-300 to-emerald-300"
            style={{ width: `${Math.max(0, Math.min(100, value * 10))}%` }}
          />
        </div>
      </div>
    </div>
  );
}

export function EvaluationPanel({ signals }: EvaluationPanelProps) {
  if (!signals) {
    return (
      <section className="panel p-4">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-300">Live Evaluation Signals</h3>
        <p className="mt-3 text-sm text-slate-300">
          AI scorecards appear as the interviewer processes each response in real time.
        </p>
      </section>
    );
  }

  return (
    <section className="panel p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-300">Live Evaluation Signals</h3>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <Score label="Technical" value={signals.technical_accuracy} />
        <Score label="Clarity" value={signals.communication_clarity} />
        <Score label="Confidence" value={signals.confidence} />
        <Score label="Overall" value={signals.overall_rating} />
      </div>
      <p className="mt-3 rounded-xl border border-cyan-300/30 bg-cyan-500/10 p-3.5 text-sm leading-relaxed text-cyan-100">
        {signals.summary_text}
      </p>
    </section>
  );
}
