"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useRef, useState } from "react";

import { Input } from "@/components/ui/input";
import {
  createRfq,
  parseRfqDocument,
  parseRfqText,
  type RfqDraft,
  type RfqPartDraft,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type PartForm = {
  part_name: string;
  category: string;
  vendor_name: string;
  vendor_id: string;
  vendor_quoted_unit_price: string;
  quantity: string;
  moq: string;
  target_unit_price: string;
  max_acceptable_unit_price: string;
  lead_time_days: string;
  payment_terms_default: string;
  spec_blurb: string;
  target_lead_time_days: string;
  max_acceptable_lead_time_days: string;
  max_acceptable_moq: string;
  preferred_payment_terms: string;
  fastest_payment_terms: string;
  min_warranty_months: string;
  alternate_vendor_name: string;
  alternate_unit_price: string;
  missing: string[];
};

function emptyPart(): PartForm {
  return {
    part_name: "",
    category: "",
    vendor_name: "",
    vendor_id: "",
    vendor_quoted_unit_price: "",
    quantity: "",
    moq: "",
    target_unit_price: "",
    max_acceptable_unit_price: "",
    lead_time_days: "",
    payment_terms_default: "Net 30",
    spec_blurb: "",
    target_lead_time_days: "",
    max_acceptable_lead_time_days: "",
    max_acceptable_moq: "",
    preferred_payment_terms: "Net 60",
    fastest_payment_terms: "Net 30",
    min_warranty_months: "24",
    alternate_vendor_name: "",
    alternate_unit_price: "",
    missing: [],
  };
}

function asText(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "";
  return String(value);
}

function partFromDraft(part: RfqPartDraft): PartForm {
  const alt = part.alternate_vendor_quotes?.[0];
  return {
    ...emptyPart(),
    part_name: part.part_name || "",
    category: part.category || "",
    vendor_name: part.vendor_name || "",
    vendor_id: part.vendor_id || "",
    vendor_quoted_unit_price: asText(part.vendor_quoted_unit_price),
    quantity: asText(part.quantity),
    moq: asText(part.moq),
    target_unit_price: asText(part.target_unit_price),
    max_acceptable_unit_price: asText(part.max_acceptable_unit_price),
    lead_time_days: asText(part.lead_time_days),
    payment_terms_default: part.payment_terms_default || "Net 30",
    spec_blurb: part.spec_blurb || "",
    target_lead_time_days: asText(part.target_lead_time_days),
    max_acceptable_lead_time_days: asText(part.max_acceptable_lead_time_days),
    max_acceptable_moq: asText(part.max_acceptable_moq),
    preferred_payment_terms: part.preferred_payment_terms || "Net 60",
    fastest_payment_terms: part.fastest_payment_terms || "Net 30",
    min_warranty_months: asText(part.min_warranty_months || 24),
    alternate_vendor_name: alt?.vendor_name || "",
    alternate_unit_price: asText(alt?.unit_price),
    missing: part.missing || [],
  };
}

function toInt(value: string): number | null {
  const trimmed = value.trim().replace(/,/g, "");
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? Math.round(parsed) : null;
}

function Field({
  label,
  hint,
  missing,
  children,
}: {
  label: string;
  hint?: string;
  missing?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span
        className={cn(
          "font-mono text-[11px] uppercase tracking-[0.18em]",
          missing ? "text-ceiling" : "text-stitch"
        )}
      >
        {label}
        {missing ? " · needed" : ""}
      </span>
      <div className="mt-1">{children}</div>
      {hint ? <p className="mt-1 text-xs text-ink/50">{hint}</p> : null}
    </label>
  );
}

const inputClass = (missing?: boolean) =>
  cn(missing && "border-ceiling focus-visible:ring-ceiling");

export default function NewRfqPage() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState("");
  const [plant, setPlant] = useState("Pune");
  const [neededBy, setNeededBy] = useState("");
  const [requestId, setRequestId] = useState("");
  const [parts, setParts] = useState<PartForm[]>([emptyPart()]);
  const [paste, setPaste] = useState("");
  const [pasteOpen, setPasteOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [filename, setFilename] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [source, setSource] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const filledCount = useMemo(() => {
    return parts.filter((part) => part.part_name && part.vendor_name && part.quantity && part.vendor_quoted_unit_price)
      .length;
  }, [parts]);

  function applyDraft(draft: RfqDraft) {
    setTitle(draft.title || title);
    setPlant(draft.plant || plant || "Pune");
    setNeededBy(draft.needed_by || neededBy);
    setRequestId(draft.request_id || requestId);
    setParts(draft.parts.length ? draft.parts.map(partFromDraft) : [emptyPart()]);
    setWarnings(draft.warnings || []);
    setSource(draft.source);
    setFilename(draft.filename);
    setError(null);
  }

  async function onFile(file: File | null) {
    if (!file || busy) return;
    setBusy("Reading the document…");
    setError(null);
    try {
      const draft = await parseRfqDocument(file, paste);
      applyDraft(draft);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read that document");
    } finally {
      setBusy(null);
    }
  }

  async function onParsePaste() {
    if (!paste.trim() || busy) return;
    setBusy("Reading the pasted RFQ…");
    setError(null);
    try {
      const draft = await parseRfqText(paste);
      applyDraft(draft);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read that text");
    } finally {
      setBusy(null);
    }
  }

  function patchPart(index: number, key: keyof PartForm, value: string) {
    setParts((current) =>
      current.map((part, i) =>
        i === index
          ? { ...part, [key]: value, missing: part.missing.filter((name) => name !== key) }
          : part
      )
    );
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy("Saving the RFQ…");
    setError(null);
    try {
      const created = await createRfq({
        request_id: requestId.trim() || undefined,
        title: title.trim(),
        plant: plant.trim() || "Pune",
        needed_by: neededBy.trim() || null,
        parts: parts.map((part) => ({
          part_name: part.part_name.trim(),
          category: part.category.trim(),
          vendor_id: part.vendor_id.trim(),
          vendor_name: part.vendor_name.trim(),
          vendor_quoted_unit_price: toInt(part.vendor_quoted_unit_price),
          quantity: toInt(part.quantity),
          moq: toInt(part.moq),
          target_unit_price: toInt(part.target_unit_price),
          max_acceptable_unit_price: toInt(part.max_acceptable_unit_price),
          lead_time_days: toInt(part.lead_time_days),
          payment_terms_default: part.payment_terms_default.trim(),
          spec_blurb: part.spec_blurb.trim(),
          target_lead_time_days: toInt(part.target_lead_time_days),
          max_acceptable_lead_time_days: toInt(part.max_acceptable_lead_time_days),
          max_acceptable_moq: toInt(part.max_acceptable_moq),
          preferred_payment_terms: part.preferred_payment_terms.trim(),
          fastest_payment_terms: part.fastest_payment_terms.trim(),
          min_warranty_months: toInt(part.min_warranty_months),
          alternate_vendor_quotes:
            part.alternate_vendor_name.trim() && toInt(part.alternate_unit_price)
              ? [
                  {
                    vendor_name: part.alternate_vendor_name.trim(),
                    unit_price: toInt(part.alternate_unit_price),
                  },
                ]
              : [],
          missing: [],
        })),
      });
      router.push(`/?added=${encodeURIComponent(created.request_id)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the RFQ");
      setBusy(null);
    }
  }

  return (
    <main className="min-h-screen bg-bone text-ink">
      <header className="flex items-end justify-between border-b border-stitch/25 px-6 py-6 md:px-10">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.28em] text-stitch">
            SKODA sourcing · new desk line
          </p>
          <h1 className="mt-2 font-display text-4xl leading-none md:text-6xl">Add an RFQ.</h1>
        </div>
        <div className="flex flex-col items-end gap-3">
          <Link
            href="/"
            className="inline-flex h-11 items-center justify-center border border-amber bg-transparent px-4 text-sm text-ink hover:bg-amber/15"
          >
            Open RFQs
          </Link>
          <p className="hidden max-w-xs text-right text-sm text-ink/70 md:block">
            Upload a quote pack or fill the form. Aria reads the document and fills every line she can
            find. Confirm the numbers before the desk goes live.
          </p>
        </div>
      </header>

      <section className="grid gap-10 px-6 py-10 md:grid-cols-[minmax(0,0.9fr)_minmax(0,1.2fr)] md:px-10">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-stitch">Document</p>
          <h2 className="mt-2 font-display text-2xl">Upload or paste.</h2>
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              void onFile(event.dataTransfer.files?.[0] || null);
            }}
            disabled={Boolean(busy)}
            className={cn(
              "mt-6 flex min-h-[180px] w-full flex-col items-start justify-end border border-dashed px-5 py-5 text-left transition-colors",
              dragging ? "border-amber bg-amber/10" : "border-stitch/40 bg-white/40 hover:border-amber hover:bg-amber/5"
            )}
          >
            <p className="font-display text-xl">
              {filename ? filename : "Drop a PDF, Word file, image, or .txt"}
            </p>
            <p className="mt-2 text-sm text-ink/60">
              {busy || "PDF, DOCX, PNG, JPG, TXT · 8 MB max. Try the sample if you want a dry run."}
            </p>
          </button>
          <input
            ref={fileRef}
            type="file"
            className="sr-only"
            accept=".pdf,.doc,.docx,.txt,.md,.csv,.png,.jpg,.jpeg,.webp"
            onChange={(event) => {
              const file = event.target.files?.[0] || null;
              event.target.value = "";
              void onFile(file);
            }}
          />
          <div className="mt-3 flex flex-wrap gap-3">
            <a
              href="/sample-rfq.txt"
              download
              className="font-mono text-[11px] uppercase tracking-[0.16em] text-amber hover:text-ink"
            >
              Download sample RFQ
            </a>
            <button
              type="button"
              onClick={() => setPasteOpen((open) => !open)}
              className="font-mono text-[11px] uppercase tracking-[0.16em] text-stitch hover:text-ink"
            >
              {pasteOpen ? "Hide paste box" : "Paste RFQ text"}
            </button>
          </div>
          {pasteOpen ? (
            <div className="mt-4">
              <textarea
                value={paste}
                onChange={(event) => setPaste(event.target.value)}
                rows={10}
                placeholder="Paste an email, quote, or RFQ…"
                className="w-full border border-stitch/30 bg-white px-3 py-3 text-sm text-ink placeholder:text-ink/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber"
              />
              <button
                type="button"
                onClick={() => void onParsePaste()}
                disabled={Boolean(busy) || !paste.trim()}
                className="mt-3 inline-flex h-11 items-center justify-center bg-ink px-4 text-sm text-bone hover:bg-pit disabled:opacity-50"
              >
                Fill form from text
              </button>
            </div>
          ) : null}
          {source ? (
            <p className="mt-4 font-mono text-[11px] uppercase tracking-[0.16em] text-ink/50">
              Filled from {source}
              {filename ? ` · ${filename}` : ""}
            </p>
          ) : null}
          {warnings.length > 0 ? (
            <ul className="mt-4 space-y-1 text-sm text-ceiling">
              {warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
        </div>

        <form onSubmit={onSubmit} className="space-y-8">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-stitch">RFQ</p>
            <h2 className="mt-2 font-display text-2xl">Confirm the request.</h2>
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <div className="md:col-span-2">
                <Field label="Title" missing={!title.trim() && Boolean(source)}>
                  <Input
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    className={inputClass(!title.trim() && Boolean(source))}
                    placeholder="Q4 fascia refresh — Pune plant"
                    required
                  />
                </Field>
              </div>
              <Field label="Plant">
                <Input value={plant} onChange={(event) => setPlant(event.target.value)} placeholder="Pune" />
              </Field>
              <Field label="Needed by">
                <Input type="date" value={neededBy} onChange={(event) => setNeededBy(event.target.value)} />
              </Field>
              <Field label="RFQ id" hint="Leave blank to assign on save.">
                <Input
                  value={requestId}
                  onChange={(event) => setRequestId(event.target.value)}
                  placeholder="rfq-2026-042"
                />
              </Field>
            </div>
          </div>

          {parts.map((part, index) => (
            <fieldset key={index} className="border border-stitch/20 bg-white/30 p-5">
              <legend className="px-2 font-mono text-[11px] uppercase tracking-[0.18em] text-stitch">
                Part line {index + 1}
              </legend>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Part name" missing={part.missing.includes("part_name")}>
                  <Input
                    value={part.part_name}
                    onChange={(event) => patchPart(index, "part_name", event.target.value)}
                    className={inputClass(part.missing.includes("part_name"))}
                    required
                  />
                </Field>
                <Field label="Category">
                  <Input
                    value={part.category}
                    onChange={(event) => patchPart(index, "category", event.target.value)}
                    placeholder="Body, Lighting, Brakes…"
                  />
                </Field>
                <Field label="Vendor" missing={part.missing.includes("vendor_name")}>
                  <Input
                    value={part.vendor_name}
                    onChange={(event) => patchPart(index, "vendor_name", event.target.value)}
                    className={inputClass(part.missing.includes("vendor_name"))}
                    required
                  />
                </Field>
                <Field label="Quoted unit price (INR)" missing={part.missing.includes("vendor_quoted_unit_price")}>
                  <Input
                    inputMode="numeric"
                    value={part.vendor_quoted_unit_price}
                    onChange={(event) => patchPart(index, "vendor_quoted_unit_price", event.target.value)}
                    className={inputClass(part.missing.includes("vendor_quoted_unit_price"))}
                    required
                  />
                </Field>
                <Field label="Quantity" missing={part.missing.includes("quantity")}>
                  <Input
                    inputMode="numeric"
                    value={part.quantity}
                    onChange={(event) => patchPart(index, "quantity", event.target.value)}
                    className={inputClass(part.missing.includes("quantity"))}
                    required
                  />
                </Field>
                <Field label="MOQ">
                  <Input
                    inputMode="numeric"
                    value={part.moq}
                    onChange={(event) => patchPart(index, "moq", event.target.value)}
                  />
                </Field>
                <Field label="Lead time (days)">
                  <Input
                    inputMode="numeric"
                    value={part.lead_time_days}
                    onChange={(event) => patchPart(index, "lead_time_days", event.target.value)}
                    placeholder="28"
                  />
                </Field>
                <Field label="Payment terms">
                  <Input
                    value={part.payment_terms_default}
                    onChange={(event) => patchPart(index, "payment_terms_default", event.target.value)}
                  />
                </Field>
                <div className="md:col-span-2">
                  <Field label="Spec">
                    <textarea
                      value={part.spec_blurb}
                      onChange={(event) => patchPart(index, "spec_blurb", event.target.value)}
                      rows={3}
                      className="w-full border border-stitch/30 bg-white px-3 py-3 text-sm text-ink placeholder:text-ink/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber"
                    />
                  </Field>
                </div>
              </div>

              <p className="mt-6 font-mono text-[11px] uppercase tracking-[0.18em] text-amber">
                SKODA envelope · never shown to the vendor
              </p>
              <div className="mt-3 grid gap-4 md:grid-cols-2">
                <Field label="Target unit price" hint="Blank = 85% of the quote.">
                  <Input
                    inputMode="numeric"
                    value={part.target_unit_price}
                    onChange={(event) => patchPart(index, "target_unit_price", event.target.value)}
                  />
                </Field>
                <Field label="Walk-away unit price" hint="Blank = 96% of the quote.">
                  <Input
                    inputMode="numeric"
                    value={part.max_acceptable_unit_price}
                    onChange={(event) => patchPart(index, "max_acceptable_unit_price", event.target.value)}
                  />
                </Field>
                <Field label="Preferred payment">
                  <Input
                    value={part.preferred_payment_terms}
                    onChange={(event) => patchPart(index, "preferred_payment_terms", event.target.value)}
                  />
                </Field>
                <Field label="Warranty (months)">
                  <Input
                    inputMode="numeric"
                    value={part.min_warranty_months}
                    onChange={(event) => patchPart(index, "min_warranty_months", event.target.value)}
                  />
                </Field>
                <Field label="Alternate vendor">
                  <Input
                    value={part.alternate_vendor_name}
                    onChange={(event) => patchPart(index, "alternate_vendor_name", event.target.value)}
                  />
                </Field>
                <Field label="Alternate unit price">
                  <Input
                    inputMode="numeric"
                    value={part.alternate_unit_price}
                    onChange={(event) => patchPart(index, "alternate_unit_price", event.target.value)}
                  />
                </Field>
              </div>
              {parts.length > 1 ? (
                <button
                  type="button"
                  onClick={() => setParts((current) => current.filter((_, i) => i !== index))}
                  className="mt-4 font-mono text-[11px] uppercase tracking-[0.16em] text-ceiling hover:text-ink"
                >
                  Remove this line
                </button>
              ) : null}
            </fieldset>
          ))}

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => setParts((current) => [...current, emptyPart()])}
              className="inline-flex h-11 items-center justify-center border border-amber bg-transparent px-4 text-sm text-ink hover:bg-amber/15"
            >
              Add another part
            </button>
            <button
              type="submit"
              disabled={Boolean(busy) || !title.trim() || filledCount === 0}
              className="inline-flex h-11 items-center justify-center bg-ink px-4 text-sm text-bone hover:bg-pit disabled:opacity-50"
            >
              {busy || "Save RFQ"}
            </button>
            <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink/50">
              {filledCount} ready line{filledCount === 1 ? "" : "s"}
            </p>
          </div>
          {error ? <p className="text-sm text-ceiling">{error}</p> : null}
        </form>
      </section>
    </main>
  );
}
