"use client";

import type { NegotiationInsight } from "@/lib/api";

function factBits(facts: Record<string, unknown>): string[] {
  const bits: string[] = [];
  if (typeof facts.counter_price === "number") bits.push(`ask ₹${facts.counter_price.toLocaleString("en-IN")}`);
  if (typeof facts.payment_terms_requested === "string") bits.push(facts.payment_terms_requested);
  if (typeof facts.moq_requested === "number") bits.push(`MOQ ${facts.moq_requested}`);
  if (typeof facts.lead_time_requested === "number") bits.push(`${facts.lead_time_requested}d lead`);
  const extra = facts.other_constraints;
  if (Array.isArray(extra)) {
    for (const item of extra) bits.push(String(item).replaceAll("_", " "));
  }
  return bits;
}

export function InsightsPanel({ insights }: { insights: NegotiationInsight[] }) {
  return (
    <section className="border-t border-bone/15 bg-pit px-6 py-5 text-bone md:max-h-72 md:overflow-y-auto md:px-8">
      <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-amber">
        Negotiation insights · SKODA only
      </p>
      <p className="mt-1 text-xs text-fog">Aria’s read of each vendor turn. Never shown to the vendor.</p>
      {insights.length === 0 ? (
        <p className="mt-3 font-mono text-[11px] uppercase tracking-[0.16em] text-fog">Waiting for a vendor message…</p>
      ) : (
        <ol className="mt-3 space-y-3">
          {insights.map((insight, index) => (
            <li key={`${insight.timestamp}-${index}`} className="border-l-2 border-amber/40 pl-3">
              <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-fog">
                r{insight.round_number}
                {insight.situation ? ` · ${insight.situation.replaceAll("_", " ")}` : ""} ·{" "}
                {insight.intent.replaceAll("_", " ")} · {insight.sentiment} · {insight.signal_confidence} conf
                {insight.tactic ? ` · ${insight.tactic.replaceAll("_", " ")}` : ""}
              </p>
              {factBits(insight.extracted_facts).length > 0 && (
                <p className="mt-1 text-xs text-bone/80">{factBits(insight.extracted_facts).join(" · ")}</p>
              )}
              {insight.reasoning && <p className="mt-1 text-xs leading-relaxed text-bone/70">{insight.reasoning}</p>}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
