"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { OpsButton, Pager, StatCard, usePagedList } from "@/components/OpsShell";
import { fetchRecentTurns, type AuditTurn } from "@/lib/ops";

const POLL_MS = 4000;

export default function LogsPage() {
  const [turns, setTurns] = useState<AuditTurn[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [role, setRole] = useState<"all" | "user" | "assistant">("all");
  const [query, setQuery] = useState("");
  const [checkedAt, setCheckedAt] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const payload = await fetchRecentTurns();
      setTurns(payload.turns);
      setError(null);
      setCheckedAt(new Date().toLocaleTimeString());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Log feed unavailable");
    }
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return turns.filter((turn) => {
      if (role !== "all" && turn.role !== role) return false;
      if (!needle) return true;
      return [turn.content, turn.reasoning, turn.session_id, turn.tactic, turn.situation, turn.model]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });
  }, [query, role, turns]);

  const turnPage = usePagedList(visible, 8, `${role}:${query}:${visible.length}`);

  return (
    <main>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-stitch">Audit stream</p>
          <h2 className="mt-1 font-display text-3xl">Logs.</h2>
        </div>
        <div className="flex items-center gap-3">
          {checkedAt ? (
            <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink/50">Live · {checkedAt}</p>
          ) : null}
          <OpsButton onClick={() => void load()} variant="ghost">
            Refresh
          </OpsButton>
        </div>
      </div>

      {error ? <p className="mt-6 text-sm text-ceiling">{error}</p> : null}

      <section className="mt-8 grid gap-4 md:grid-cols-3">
        <StatCard label="Recent turns" value={turns.length} hint="Last 200 across desks" />
        <StatCard
          label="Assistant"
          value={turns.filter((turn) => turn.role === "assistant").length}
          hint="Aria replies + reasoning"
        />
        <StatCard
          label="Vendor"
          value={turns.filter((turn) => turn.role === "user").length}
          hint="Inbound desk messages"
        />
      </section>

      <div className="mt-8 flex flex-wrap gap-2">
        {(["all", "assistant", "user"] as const).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setRole(value)}
            className={`h-10 px-4 font-mono text-[11px] uppercase tracking-[0.16em] ${
              role === value ? "bg-ink text-bone" : "border border-stitch/30 text-ink hover:bg-amber/15"
            }`}
          >
            {value === "user" ? "vendor" : value}
          </button>
        ))}
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search content, reasoning, tactic, model"
          className="h-10 min-w-[16rem] flex-1 border border-stitch/30 bg-transparent px-3 text-sm outline-none focus:border-amber"
        />
      </div>

      <ol className="mt-6 divide-y divide-stitch/20 border-y border-stitch/20">
        {visible.length === 0 ? (
          <li className="py-6 text-sm text-ink/60">No turns match the filter.</li>
        ) : (
          turnPage.slice.map((turn, index) => (
            <li key={`${turn.id ?? index}-${turn.session_id}`} className="py-5">
              <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-stitch">
                {turn.role} · {turn.session_id.slice(0, 8)} · {turn.stage || "—"} · {turn.model || "unmodeled"}
                {turn.tactic ? ` · ${turn.tactic}` : ""}
                {turn.situation ? ` · ${turn.situation}` : ""}
              </p>
              <p className="mt-2 text-sm">{turn.content}</p>
              {turn.reasoning ? (
                <p className="mt-2 border-l-2 border-amber pl-3 text-sm text-ink/60">{turn.reasoning}</p>
              ) : null}
              <p className="mt-2 font-mono text-[11px] text-ink/40">{turn.created_at}</p>
            </li>
          ))
        )}
      </ol>
      <Pager
        page={turnPage.page}
        pages={turnPage.pages}
        total={turnPage.total}
        pageSize={turnPage.pageSize}
        onPage={turnPage.setPage}
        noun="turns"
      />
    </main>
  );
}
