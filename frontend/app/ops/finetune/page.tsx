"use client";

import { useCallback, useEffect, useState } from "react";

import { OpsButton, Pager, StatCard, usePagedList } from "@/components/OpsShell";
import {
  asList,
  fetchFineTunePreview,
  fetchFineTuneStatus,
  fetchHealth,
  patchFineTuneSettings,
  postFineTuneExport,
  postFineTuneSubmit,
  postFineTuneTick,
  type FineTuneConfig,
  type FineTuneStatus,
  type HealthPayload,
} from "@/lib/ops";

type CheckResult = { name: string; ok: boolean; detail: string };

export default function FineTunePage() {
  const [status, setStatus] = useState<FineTuneStatus | null>(null);
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionNote, setActionNote] = useState<string | null>(null);
  const [checks, setChecks] = useState<CheckResult[]>([]);
  const [checkedAt, setCheckedAt] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [draft, setDraft] = useState<FineTuneConfig | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const [nextStatus, nextHealth] = await Promise.all([fetchFineTuneStatus(), fetchHealth()]);
      setStatus(nextStatus);
      setHealth(nextHealth);
      setError(null);
      setCheckedAt(new Date().toLocaleTimeString());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fine-tune status unavailable");
    }
  }, []);

  useEffect(() => {
    if (!status?.config || dirty) return;
    setDraft(status.config);
  }, [dirty, status]);

  useEffect(() => {
    if (dirty) setSettingsOpen(true);
  }, [dirty]);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(id);
  }, [load]);

  const preview = status?.preview;
  const trainExamples = preview?.train_examples ?? 0;
  const minExamples = status?.min_examples ?? 20;
  const ready = Boolean(status?.ready);
  const openJob = status?.open_job as Record<string, unknown> | null;
  const lastJob = status?.last_job as Record<string, unknown> | null;
  const labelPage = usePagedList(status?.labels || [], 8, (status?.labels || []).length);
  const jobPage = usePagedList(status?.jobs || [], 8, (status?.jobs || []).length);

  async function run(name: string, work: () => Promise<unknown>) {
    setBusy(name);
    setActionNote(null);
    try {
      const result = await work();
      setActionNote(`${name} completed.`);
      await load();
      return result;
    } catch (err) {
      setActionNote(err instanceof Error ? err.message : `${name} failed`);
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function runChecks() {
    setBusy("checks");
    const results: CheckResult[] = [];
    try {
      const liveHealth = await fetchHealth();
      results.push({
        name: "Health",
        ok: liveHealth.ok && !liveHealth.is_mock,
        detail: liveHealth.is_mock
          ? "Provider is mock — live replies will not train useful voice."
          : `${liveHealth.provider} · chat ${liveHealth.chat_model} · reason ${liveHealth.reasoning_model}`,
      });
    } catch (err) {
      results.push({
        name: "Health",
        ok: false,
        detail: err instanceof Error ? err.message : "Health failed",
      });
    }
    try {
      const liveStatus = await fetchFineTuneStatus();
      results.push({
        name: "Status",
        ok: true,
        detail: `auto=${liveStatus.auto} · ${liveStatus.preview.train_examples}/${liveStatus.min_examples} examples · chat ${liveStatus.active_chat_model}`,
      });
    } catch (err) {
      results.push({
        name: "Status",
        ok: false,
        detail: err instanceof Error ? err.message : "Status failed",
      });
    }
    try {
      const livePreview = await fetchFineTunePreview();
      results.push({
        name: "Preview",
        ok: Boolean(livePreview.train_examples || livePreview.closed_sessions),
        detail: `${livePreview.train_examples ?? 0} train voice · ${livePreview.valid_examples ?? 0} valid · ${livePreview.skipped_sessions ?? 0} skipped`,
      });
    } catch (err) {
      results.push({
        name: "Preview",
        ok: false,
        detail: err instanceof Error ? err.message : "Preview failed",
      });
    }
    setChecks(results);
    setBusy(null);
    await load();
  }

  function edit<K extends keyof FineTuneConfig>(key: K, value: FineTuneConfig[K]) {
    setDirty(true);
    setDraft((current) =>
      current
        ? { ...current, [key]: value }
        : ({
            auto: true,
            base_model: "gpt-4o-mini",
            min_examples: 20,
            suffix: "aria-voice",
            n_epochs: null,
            auto_promote: true,
            tick_seconds: 90,
            allowed_base_models: ["gpt-4o-mini"],
            openai_floor: 10,
            source: "env",
            [key]: value,
          } as FineTuneConfig)
    );
  }

  async function saveSettings() {
    if (!draft) return;
    setBusy("save");
    setActionNote(null);
    try {
      await patchFineTuneSettings({
        auto: draft.auto,
        min_examples: draft.min_examples,
        base_model: draft.base_model,
        suffix: draft.suffix,
        n_epochs: draft.n_epochs ?? "auto",
        auto_promote: draft.auto_promote,
        tick_seconds: draft.tick_seconds,
      });
      setDirty(false);
      setActionNote("Settings saved. Next tick / preview / submit uses them.");
      await load();
    } catch (err) {
      setActionNote(err instanceof Error ? err.message : "Could not save settings");
    } finally {
      setBusy(null);
    }
  }

  return (
    <main>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-stitch">Voice pipeline</p>
          <h2 className="mt-1 font-display text-3xl">Fine-tune.</h2>
          <p className="mt-3 max-w-2xl text-sm text-ink/70">
            Closed desks are labeled train or reject. OpenAI will take a job from 10 examples. {minExamples} is the
            current bar — editable below. 20 is a start, not a quality lift; 50–100+ clean turns is the first useful
            range. o4-mini stays the commercial brain and is never submitted.
          </p>
        </div>
        <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink/50">
          {checkedAt ? `Status · ${checkedAt}` : "Loading"}
        </p>
      </div>

      {error ? <p className="mt-6 text-sm text-ceiling">{error}</p> : null}
      {actionNote ? <p className="mt-4 text-sm text-ink/70">{actionNote}</p> : null}

      <section className="mt-8 grid gap-4 md:grid-cols-4">
        <StatCard
          label="Ready"
          value={ready ? "yes" : "not yet"}
          hint={`${trainExamples} / ${minExamples} train examples`}
          tone={ready ? "deal" : "amber"}
        />
        <StatCard
          label="Auto"
          value={status?.auto ? "on" : "off"}
          hint={health?.is_mock ? "Mock provider — no live job" : "Ticks after close + every 90s"}
          tone={status?.auto ? "deal" : "ceiling"}
        />
        <StatCard
          label="Chat model"
          value={shortModel(status?.active_chat_model)}
          hint="Promoted fine-tune replaces gpt-4o voice"
        />
        <StatCard
          label="Open job"
          value={openJob ? String(openJob.status || "open") : "none"}
          hint={openJob ? String(openJob.job_id || "") : "No OpenAI job in flight"}
          tone={openJob ? "amber" : "default"}
        />
      </section>

      <section className="mt-8 grid gap-4 md:grid-cols-4">
        <StatCard label="Train labels" value={status?.label_counts?.train ?? 0} tone="deal" />
        <StatCard label="Reject labels" value={status?.label_counts?.reject ?? 0} tone="ceiling" />
        <StatCard label="Valid split" value={preview?.valid_examples ?? 0} />
        <StatCard label="Skipped desks" value={preview?.skipped_sessions ?? 0} />
      </section>

      <section className="mt-10 border border-stitch/25 p-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <button
            type="button"
            aria-expanded={settingsOpen}
            onClick={() => setSettingsOpen((open) => !open)}
            className="text-left"
          >
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-stitch">
              Settings · {settingsOpen ? "hide" : "show"}
            </p>
            <p className="mt-2 max-w-3xl text-sm text-ink/70">
              {settingsOpen
                ? status?.guidance?.note ||
                  "Saved here, used by preview, tick, export, submit, and the background loop. Overlay wins over .env."
                : `${status?.auto ? "Auto on" : "Auto off"} · min ${minExamples} · ${status?.base_model || "gpt-4o-mini"} · tick ${draft?.tick_seconds ?? 90}s`}
            </p>
          </button>
          {settingsOpen || dirty ? (
            <OpsButton disabled={Boolean(busy) || !draft || !dirty} onClick={() => void saveSettings()}>
              {busy === "save" ? "Saving…" : dirty ? "Save changes" : "Saved"}
            </OpsButton>
          ) : null}
        </div>
        {settingsOpen ? (
          draft ? (
            <div className="mt-6 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            <label className="block text-sm">
              <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-stitch">Auto-submit</span>
              <select
                className="mt-2 h-11 w-full border border-stitch/30 bg-transparent px-3 outline-none focus:border-amber"
                value={draft.auto ? "on" : "off"}
                onChange={(event) => edit("auto", event.target.value === "on")}
              >
                <option value="on">On — submit when the bar is met</option>
                <option value="off">Off — tick labels only</option>
              </select>
            </label>
            <label className="block text-sm">
              <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-stitch">Min train examples</span>
              <input
                type="number"
                min={10}
                max={2000}
                value={draft.min_examples}
                onChange={(event) => edit("min_examples", Number(event.target.value))}
                className="mt-2 h-11 w-full border border-stitch/30 bg-transparent px-3 outline-none focus:border-amber"
              />
              <span className="mt-2 flex flex-wrap gap-2">
                {[10, 20, 50, 100, 200].map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => edit("min_examples", n)}
                    className={`h-8 px-3 font-mono text-[11px] uppercase tracking-[0.14em] ${
                      draft.min_examples === n ? "bg-ink text-bone" : "border border-stitch/30 hover:bg-amber/15"
                    }`}
                  >
                    {n}
                  </button>
                ))}
              </span>
            </label>
            <label className="block text-sm">
              <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-stitch">Voice base model</span>
              <select
                className="mt-2 h-11 w-full border border-stitch/30 bg-transparent px-3 outline-none focus:border-amber"
                value={draft.base_model}
                onChange={(event) => edit("base_model", event.target.value)}
              >
                {(draft.allowed_base_models.length ? draft.allowed_base_models : ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o"]).map(
                  (model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  )
                )}
              </select>
            </label>
            <label className="block text-sm">
              <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-stitch">Job suffix</span>
              <input
                value={draft.suffix}
                maxLength={18}
                onChange={(event) => edit("suffix", event.target.value)}
                className="mt-2 h-11 w-full border border-stitch/30 bg-transparent px-3 outline-none focus:border-amber"
              />
            </label>
            <label className="block text-sm">
              <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-stitch">Epochs</span>
              <select
                className="mt-2 h-11 w-full border border-stitch/30 bg-transparent px-3 outline-none focus:border-amber"
                value={draft.n_epochs == null ? "auto" : String(draft.n_epochs)}
                onChange={(event) =>
                  edit("n_epochs", event.target.value === "auto" ? null : Number(event.target.value))
                }
              >
                <option value="auto">Auto</option>
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-stitch">Promote on success</span>
              <select
                className="mt-2 h-11 w-full border border-stitch/30 bg-transparent px-3 outline-none focus:border-amber"
                value={draft.auto_promote ? "on" : "off"}
                onChange={(event) => edit("auto_promote", event.target.value === "on")}
              >
                <option value="on">On — swap chat model to the new ft:</option>
                <option value="off">Off — leave gpt-4o until you promote</option>
              </select>
            </label>
            <label className="block text-sm">
              <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-stitch">Background tick (seconds)</span>
              <input
                type="number"
                min={15}
                max={3600}
                value={draft.tick_seconds}
                onChange={(event) => edit("tick_seconds", Number(event.target.value))}
                className="mt-2 h-11 w-full border border-stitch/30 bg-transparent px-3 outline-none focus:border-amber"
              />
            </label>
          </div>
          ) : (
            <p className="mt-4 text-sm text-ink/50">Loading settings…</p>
          )
        ) : null}
      </section>

      <section className="mt-10">
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-stitch">Controls</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <OpsButton disabled={Boolean(busy)} onClick={() => void run("Tick", postFineTuneTick)}>
            {busy === "Tick" ? "Ticking…" : "Tick pipeline"}
          </OpsButton>
          <OpsButton variant="ghost" disabled={Boolean(busy)} onClick={() => void run("Export", postFineTuneExport)}>
            {busy === "Export" ? "Exporting…" : "Export JSONL"}
          </OpsButton>
          <OpsButton
            danger
            disabled={Boolean(busy) || !ready}
            onClick={() => {
              const ok = window.confirm(
                "Force submit starts a paid OpenAI fine-tune job if the threshold is met. Continue?"
              );
              if (!ok) return;
              void run("Force submit", postFineTuneSubmit);
            }}
          >
            {busy === "Force submit" ? "Submitting…" : "Force submit"}
          </OpsButton>
          <OpsButton variant="ghost" disabled={Boolean(busy)} onClick={() => void load()}>
            Refresh status
          </OpsButton>
        </div>
        <p className="mt-3 max-w-3xl text-sm text-ink/60">
          Tick labels new desks and polls any open job. Export writes JSONL under backend/data/finetune without starting
          a job. Force submit spends money — only use it when the desk is ready.
        </p>
      </section>

      <section className="mt-10 border border-stitch/25 p-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-stitch">Testing</p>
            <p className="mt-2 text-sm text-ink/70">
              Runs health, status, and preview only. Use Tick pipeline to label desks. Force submit is the paid job.
            </p>
          </div>
          <OpsButton variant="ghost" disabled={Boolean(busy)} onClick={() => void runChecks()}>
            {busy === "checks" ? "Checking…" : "Run checks"}
          </OpsButton>
        </div>
        <ul className="mt-5 space-y-3">
          {checks.length === 0 ? (
            <li className="text-sm text-ink/50">No test run yet.</li>
          ) : (
            checks.map((check) => (
              <li key={check.name} className="flex flex-wrap gap-3 text-sm">
                <span
                  className={`font-mono text-[11px] uppercase tracking-[0.16em] ${
                    check.ok ? "text-deal" : "text-ceiling"
                  }`}
                >
                  {check.ok ? "pass" : "fail"}
                </span>
                <span className="font-medium">{check.name}</span>
                <span className="text-ink/70">{check.detail}</span>
              </li>
            ))
          )}
        </ul>
      </section>

      <section className="mt-10 grid gap-8 lg:grid-cols-2">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-stitch">Labels</p>
          <ul className="mt-4 divide-y divide-stitch/20 border-y border-stitch/20">
            {(status?.labels || []).length === 0 ? (
              <li className="py-4 text-sm text-ink/60">Close a few desks to collect labels.</li>
            ) : (
              labelPage.slice.map((row) => (
                <li key={row.session_id} className="py-4">
                  <p className="font-display text-xl">
                    {row.session_id.slice(0, 8)} · {row.quality}
                  </p>
                  <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-stitch">
                    {row.outcome || "—"} · {row.voice_examples ?? 0} voice
                  </p>
                  <p className="mt-1 text-sm text-ink/65">{asList(row.reasons).join(" · ") || "clean"}</p>
                </li>
              ))
            )}
          </ul>
          <Pager
            page={labelPage.page}
            pages={labelPage.pages}
            total={labelPage.total}
            pageSize={labelPage.pageSize}
            onPage={labelPage.setPage}
            noun="labels"
          />
        </div>
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-stitch">Jobs</p>
          <ul className="mt-4 divide-y divide-stitch/20 border-y border-stitch/20">
            {(status?.jobs || []).length === 0 ? (
              <li className="py-4 text-sm text-ink/60">
                {lastJob ? `Last job ${String(lastJob.status || "")}` : "No OpenAI jobs recorded yet."}
              </li>
            ) : (
              jobPage.slice.map((job) => (
                <li key={String(job.job_id)} className="py-4">
                  <p className="font-display text-xl">{String(job.status)}</p>
                  <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-stitch">
                    {String(job.job_id || "").slice(0, 24)} · {String(job.base_model || "")}
                  </p>
                  {job.fine_tuned_model ? (
                    <p className="mt-1 text-sm text-deal">{String(job.fine_tuned_model)}</p>
                  ) : null}
                  {job.error ? <p className="mt-1 text-sm text-ceiling">{String(job.error)}</p> : null}
                </li>
              ))
            )}
          </ul>
          <Pager
            page={jobPage.page}
            pages={jobPage.pages}
            total={jobPage.total}
            pageSize={jobPage.pageSize}
            onPage={jobPage.setPage}
            noun="jobs"
          />
        </div>
      </section>
    </main>
  );
}

function shortModel(value?: string | null) {
  if (!value) return "—";
  if (value.startsWith("ft:")) return `ft · ${value.split(":").slice(-1)[0] || "custom"}`;
  return value;
}
