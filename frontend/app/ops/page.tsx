"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { OpsButton, Pager, StatCard, usePagedList } from "@/components/OpsShell";
import { fetchOverview, type OpsOverview } from "@/lib/ops";

const POLL_MS = 4000;

export default function OpsOverviewPage() {
  const [data, setData] = useState<OpsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checkedAt, setCheckedAt] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const next = await fetchOverview();
      setData(next);
      setError(null);
      setCheckedAt(new Date().toLocaleTimeString());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Overview unavailable");
    }
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  const health = data?.health;
  const pipeline = data?.pipeline;
  const counts = data?.counts;
  const live = Boolean(health && !health.is_mock && health.ok);
  const train = pipeline?.label_counts?.train ?? 0;
  const reject = pipeline?.label_counts?.reject ?? 0;
  const examples = pipeline?.train_examples ?? 0;
  const minExamples = pipeline?.min_examples ?? 20;
  const desks = data?.sessions || [];
  const deskPage = usePagedList(desks, 8, desks.length);

  return (
    <main>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-stitch">Overall status</p>
          <h2 className="mt-1 font-display text-3xl">Health, counts, pipeline.</h2>
        </div>
        <div className="flex items-center gap-3">
          {checkedAt ? (
            <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink/50">Live · {checkedAt}</p>
          ) : null}
          <OpsButton onClick={() => void load()} variant="ghost">
            Recheck
          </OpsButton>
        </div>
      </div>

      {error ? <p className="mt-6 text-sm text-ceiling">{error}. Start the API, then recheck.</p> : null}

      <section className="mt-8 grid gap-4 md:grid-cols-4">
        <StatCard
          label="API"
          value={health?.ok ? "up" : "down"}
          hint={health ? `${health.company} · :${health.port}` : "Waiting for health"}
          tone={health?.ok ? "deal" : "ceiling"}
        />
        <StatCard
          label="LLM"
          value={health?.is_mock ? "mock" : health?.provider || "—"}
          hint={live ? `chat ${health?.chat_model || "—"}` : "Live key required for vendor replies"}
          tone={live ? "deal" : "ceiling"}
        />
        <StatCard
          label="Reasoning"
          value={health?.reasoning_model || "—"}
          hint="Commercial brain. Not fine-tuned."
          tone="amber"
        />
        <StatCard
          label="Fine-tune"
          value={pipeline?.ready ? "ready" : `${examples}/${minExamples}`}
          hint={
            pipeline?.guidance?.band === "thin"
              ? `${examples}/${minExamples} · thin set — raise the bar on Fine-tune`
              : pipeline?.auto
                ? "Auto pipeline on"
                : "Auto pipeline off"
          }
          tone={pipeline?.ready ? "deal" : "amber"}
        />
      </section>

      <section className="mt-8 grid gap-4 md:grid-cols-4">
        <StatCard label="Sessions" value={counts?.sessions ?? "—"} hint="Closed and open desks" />
        <StatCard label="Turns" value={counts?.turns ?? "—"} hint="Vendor + Aria messages" />
        <StatCard label="Lessons" value={counts?.lessons ?? "—"} hint="Playbook memory" />
        <StatCard label="Labels" value={counts?.labels ?? "—"} hint={`${train} train · ${reject} reject`} />
      </section>

      <section className="mt-10 grid gap-8 lg:grid-cols-[1.2fr_0.8fr]">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-stitch">Recent desks</p>
          <ul className="mt-4 divide-y divide-stitch/20 border-y border-stitch/20">
            {desks.length === 0 ? (
              <li className="py-4 text-sm text-ink/60">No sessions in the audit log yet.</li>
            ) : (
              deskPage.slice.map((row) => (
                <li key={row.session_id} className="flex flex-wrap items-baseline justify-between gap-3 py-4">
                  <div>
                    <p className="font-display text-xl">{row.part_id || "unknown part"}</p>
                    <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-stitch">
                      {row.session_id.slice(0, 8)} · {row.stage?.replaceAll("_", " ")} · {row.round_count ?? 0} rounds
                    </p>
                  </div>
                  <Link
                    href={`/ops/data?session=${encodeURIComponent(row.session_id)}`}
                    className="font-mono text-[11px] uppercase tracking-[0.16em] text-amber hover:text-ink"
                  >
                    Open in data
                  </Link>
                </li>
              ))
            )}
          </ul>
          <Pager
            page={deskPage.page}
            pages={deskPage.pages}
            total={deskPage.total}
            pageSize={deskPage.pageSize}
            onPage={deskPage.setPage}
            noun="desks"
          />
        </div>
        <div className="border border-stitch/25 p-5">
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-stitch">Checks</p>
          <ul className="mt-4 space-y-3 text-sm">
            <Check ok={Boolean(health?.ok)} label="FastAPI /health responds" />
            <Check ok={live} label="Live OpenAI provider (not mock)" />
            <Check ok={Boolean(health?.chat_model)} label={`Chat model ${health?.chat_model || "unset"}`} />
            <Check ok={Boolean(health?.reasoning_model)} label={`Reasoning model ${health?.reasoning_model || "unset"}`} />
            <Check ok={Boolean(pipeline?.auto)} label="Fine-tune auto tick enabled" />
            <Check ok={!pipeline?.open_job} label={pipeline?.open_job ? "OpenAI job in flight" : "No open fine-tune job"} />
            <Check ok={(counts?.catalog_parts ?? 0) > 0} label={`${counts?.catalog_parts ?? 0} catalog parts`} />
          </ul>
          <p className="mt-6 font-mono text-[11px] uppercase tracking-[0.16em] text-ink/40">
            Audit · {data?.audit_db || "local sqlite"}
          </p>
        </div>
      </section>
    </main>
  );
}

function Check({ ok, label }: { ok: boolean; label: string }) {
  return (
    <li className="flex gap-3">
      <span className={`font-mono text-[11px] uppercase tracking-[0.16em] ${ok ? "text-deal" : "text-ceiling"}`}>
        {ok ? "pass" : "watch"}
      </span>
      <span>{label}</span>
    </li>
  );
}
