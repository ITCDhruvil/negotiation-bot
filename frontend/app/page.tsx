"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { fetchCatalog, type CatalogRequest } from "@/lib/api";
import { formatInr } from "@/lib/utils";

const TEN_LAKH = 1_000_000;

export default function HomePage() {
  const [requests, setRequests] = useState<CatalogRequest[]>([]);
  const [company, setCompany] = useState("SKODA");
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<string | null>(null);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("added");
    if (id) setAdded(id);
    fetchCatalog()
      .then((data) => {
        setCompany(data.company);
        setRequests(data.requests);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Catalog unavailable"));
  }, []);

  return (
    <main className="min-h-screen bg-bone text-ink">
      <header className="flex items-end justify-between border-b border-stitch/25 px-6 py-6 md:px-10">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.28em] text-stitch">
            {company} sourcing · Pune
          </p>
          <h1 className="mt-2 font-display text-4xl leading-none md:text-6xl">Open RFQs.</h1>
        </div>
        <div className="flex flex-col items-end gap-3">
          <div className="flex flex-wrap justify-end gap-2">
            <Link
              href="/rfq/new"
              className="inline-flex h-11 items-center justify-center bg-ink px-4 text-sm text-bone hover:bg-pit"
            >
              Add RFQ
            </Link>
            <Link
              href="/ops"
              className="inline-flex h-11 items-center justify-center border border-amber bg-transparent px-4 text-sm text-ink hover:bg-amber/15"
            >
              Ops
            </Link>
          </div>
          <p className="hidden max-w-xs text-right text-sm text-ink/70 md:block">
            Aria negotiates with vendor desks, one part-vendor line at a time, inside a hard ₹10,00,000
            order-total ceiling. She&apos;s an AI. The numbers are not.
          </p>
        </div>
      </header>
      <section className="px-6 py-10 md:px-10">
        {added && (
          <p className="mb-8 border border-deal/30 bg-deal/10 px-4 py-3 text-sm text-deal">
            RFQ {added} is on the desk. Open Negotiate on a line to start Aria.
          </p>
        )}
        {error && <p className="text-sm text-ceiling">{error}. Start the API on :8000.</p>}
        {requests.map((req) => (
          <div key={req.request_id} className="mb-12">
            <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-stitch">
              {req.request_id} · {req.plant}
            </p>
            <h2 className="mt-2 font-display text-2xl">{req.title}</h2>
            <ul className="mt-6 divide-y divide-stitch/20 border-y border-stitch/20">
              {req.parts.map((part) => {
                const quotedTotal = part.vendor_quoted_unit_price * part.quantity;
                const overCeiling = quotedTotal > TEN_LAKH;
                return (
                  <li
                    key={part.part_id}
                    className="grid gap-4 py-6 md:grid-cols-[1.5fr_0.9fr_auto] md:items-center"
                  >
                    <div>
                      <p className="font-display text-2xl">{part.part_name}</p>
                      <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-stitch">
                        {part.vendor_name} · {part.quantity} units
                      </p>
                    </div>
                    <div>
                      <p className="font-mono text-xl">{formatInr(part.vendor_quoted_unit_price)} / unit</p>
                      <p className="text-sm text-ink/60">
                        {overCeiling
                          ? `Quoted total ${formatInr(quotedTotal)} · above automated ceiling`
                          : `Quoted total ${formatInr(quotedTotal)}`}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Link
                        href={`/chat?part=${part.part_id}`}
                        className="inline-flex h-11 items-center justify-center bg-ink px-4 text-sm text-bone hover:bg-pit"
                      >
                        Negotiate
                      </Link>
                      <Link
                        href={`/chat?part=${part.part_id}&demo=1`}
                        className="inline-flex h-11 items-center justify-center border border-amber bg-transparent px-4 text-sm text-ink hover:bg-amber/15"
                      >
                        Test
                      </Link>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </section>
    </main>
  );
}
