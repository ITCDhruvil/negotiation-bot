"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { OpsButton, Pager, StatCard, usePagedList } from "@/components/OpsShell";
import {
  asList,
  fetchLabels,
  fetchLessons,
  fetchLoggedSessions,
  fetchSessionLog,
  type LabelRow,
  type LessonRow,
  type SessionLog,
  type SessionRow,
} from "@/lib/ops";
import { formatInr } from "@/lib/utils";

const POLL_MS = 4000;

function DataInner() {
  const params = useSearchParams();
  const preset = params.get("session");
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [lessons, setLessons] = useState<LessonRow[]>([]);
  const [labels, setLabels] = useState<LabelRow[]>([]);
  const [selected, setSelected] = useState<string | null>(preset);
  const [log, setLog] = useState<SessionLog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checkedAt, setCheckedAt] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const load = useCallback(async () => {
    try {
      const [sessionPayload, lessonPayload, labelPayload] = await Promise.all([
        fetchLoggedSessions(),
        fetchLessons(),
        fetchLabels(),
      ]);
      setSessions(sessionPayload.sessions);
      setLessons(lessonPayload.lessons);
      setLabels(labelPayload.labels);
      setError(null);
      setCheckedAt(new Date().toLocaleTimeString());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Data feed unavailable");
    }
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  useEffect(() => {
    if (preset) setSelected(preset);
  }, [preset]);

  useEffect(() => {
    if (!selected) {
      setLog(null);
      return;
    }
    fetchSessionLog(selected)
      .then(setLog)
      .catch(() => setLog(null));
  }, [selected]);

  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return sessions;
    return sessions.filter((row) =>
      [row.session_id, row.part_id, row.stage, row.vendor_company, row.vendor_rep_name]
        .join(" ")
        .toLowerCase()
        .includes(needle)
    );
  }, [filter, sessions]);

  const train = labels.filter((row) => row.quality === "train").length;
  const reject = labels.filter((row) => row.quality === "reject").length;
  const sessionPage = usePagedList(visible, 8, `${filter}:${visible.length}`);
  const lessonPage = usePagedList(lessons, 8, lessons.length);
  const turnPage = usePagedList(log?.turns || [], 6, selected || "");

  return (
    <main>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-stitch">Collected desks</p>
          <h2 className="mt-1 font-display text-3xl">Live data.</h2>
        </div>
        <div className="flex items-center gap-3">
          {checkedAt ? (
            <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink/50">Refreshing · {checkedAt}</p>
          ) : null}
          <OpsButton onClick={() => void load()} variant="ghost">
            Refresh
          </OpsButton>
        </div>
      </div>

      {error ? <p className="mt-6 text-sm text-ceiling">{error}</p> : null}

      <section className="mt-8 grid gap-4 md:grid-cols-4">
        <StatCard label="Desks" value={sessions.length} hint="Audit snapshots" />
        <StatCard label="Lessons" value={lessons.length} hint="Reusable tactics" />
        <StatCard label="Train" value={train} hint="Eligible for voice JSONL" tone="deal" />
        <StatCard label="Reject" value={reject} hint="Leak, short, or not closed" tone="ceiling" />
      </section>

      <div className="mt-8">
        <input
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder="Filter by part, vendor, stage, session"
          className="h-11 w-full border border-stitch/30 bg-transparent px-3 text-sm outline-none focus:border-amber"
        />
      </div>

      <section className="mt-6 grid gap-8 lg:grid-cols-[1fr_1fr]">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-stitch">Sessions</p>
          <ul className="mt-4 divide-y divide-stitch/20 border-y border-stitch/20">
            {visible.length === 0 ? (
              <li className="py-4 text-sm text-ink/60">No matching desks.</li>
            ) : (
              sessionPage.slice.map((row) => (
                <li key={row.session_id}>
                  <button
                    type="button"
                    onClick={() => setSelected(row.session_id)}
                    className={`w-full py-4 text-left ${selected === row.session_id ? "bg-amber/10" : ""}`}
                  >
                    <p className="font-display text-xl">{row.part_id}</p>
                    <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-stitch">
                      {row.stage?.replaceAll("_", " ")} · {row.round_count ?? 0} rounds
                      {row.vendor_rep_name ? ` · ${row.vendor_rep_name}` : ""}
                    </p>
                    <p className="mt-1 text-sm text-ink/60">
                      Aria {row.current_bot_offer != null ? formatInr(row.current_bot_offer) : "—"} · vendor{" "}
                      {row.current_vendor_offer != null ? formatInr(row.current_vendor_offer) : "—"}
                    </p>
                  </button>
                </li>
              ))
            )}
          </ul>
          <Pager
            page={sessionPage.page}
            pages={sessionPage.pages}
            total={sessionPage.total}
            pageSize={sessionPage.pageSize}
            onPage={sessionPage.setPage}
            noun="desks"
          />
        </div>
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-stitch">Desk detail</p>
          {!log ? (
            <p className="mt-4 text-sm text-ink/60">Select a session to inspect turns, insights, and its label.</p>
          ) : (
            <div className="mt-4 border border-stitch/25 p-4">
              <p className="font-display text-2xl">{log.part_id || selected}</p>
              <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-stitch">
                {log.stage?.replaceAll("_", " ") || "logged"} · {log.round_count ?? log.turns.length} ·{" "}
                {log.label?.quality || "unlabeled"}
              </p>
              {log.label ? (
                <p className="mt-2 text-sm text-ink/70">
                  {asList(log.label.reasons).join(" · ") || "No reject reasons"}
                </p>
              ) : null}
              <ol className="mt-4 space-y-3">
                {turnPage.slice.map((turn, index) => (
                  <li key={`${turn.session_id}-${index}`} className="border-t border-stitch/15 pt-3">
                    <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-stitch">
                      {turn.role} {turn.tactic ? `· ${turn.tactic}` : ""} {turn.situation ? `· ${turn.situation}` : ""}
                    </p>
                    <p className="mt-1 text-sm">{turn.content}</p>
                    {turn.reasoning ? <p className="mt-1 text-sm text-ink/55">{turn.reasoning}</p> : null}
                  </li>
                ))}
              </ol>
              <Pager
                page={turnPage.page}
                pages={turnPage.pages}
                total={turnPage.total}
                pageSize={turnPage.pageSize}
                onPage={turnPage.setPage}
                noun="turns"
              />
            </div>
          )}
        </div>
      </section>

      <section className="mt-12">
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-stitch">Playbook lessons</p>
        <ul className="mt-4 divide-y divide-stitch/20 border-y border-stitch/20">
          {lessons.length === 0 ? (
            <li className="py-4 text-sm text-ink/60">Lessons appear after a desk closes without a walk-away leak.</li>
          ) : (
            lessonPage.slice.map((lesson) => (
              <li key={lesson.id} className="py-4">
                <p className="font-display text-xl">
                  {lesson.part_name || lesson.part_id} · {lesson.situation}
                </p>
                <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-stitch">
                  {lesson.outcome} · {asList(lesson.tactics).join(" · ") || "no tactics"}
                </p>
                {lesson.note ? <p className="mt-1 text-sm text-ink/70">{lesson.note}</p> : null}
              </li>
            ))
          )}
        </ul>
        <Pager
          page={lessonPage.page}
          pages={lessonPage.pages}
          total={lessonPage.total}
          pageSize={lessonPage.pageSize}
          onPage={lessonPage.setPage}
          noun="lessons"
        />
      </section>
    </main>
  );
}

export default function DataPage() {
  return (
    <Suspense
      fallback={
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink/50">Opening the data desk…</p>
      }
    >
      <DataInner />
    </Suspense>
  );
}
