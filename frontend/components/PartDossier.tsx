import { formatInr } from "@/lib/utils";
import type { PublicPart } from "@/lib/api";

export function PartDossier({ part }: { part: PublicPart }) {
  const quotedTotal = part.vendor_quoted_unit_price * part.quantity;
  return (
    <section className="flex h-full flex-col bg-pit px-6 py-8 text-bone md:px-8">
      <p className="font-mono text-[11px] uppercase tracking-[0.28em] text-amber">
        {part.request_id} · {part.plant}
      </p>
      <h1 className="mt-6 font-display text-4xl leading-none tracking-tight md:text-5xl">{part.part_name}</h1>
      <p className="mt-2 font-mono text-sm uppercase tracking-[0.2em] text-fog">{part.vendor_name}</p>
      <p className="mt-8 font-mono text-3xl text-amber">{formatInr(part.vendor_quoted_unit_price)}</p>
      <p className="mt-1 text-sm text-fog">Vendor quote · per unit</p>
      <dl className="mt-8 grid grid-cols-2 gap-x-4 gap-y-3 font-mono text-sm text-bone/90">
        <div>
          <dt className="text-[10px] uppercase tracking-[0.18em] text-fog">Qty</dt>
          <dd>{part.quantity}</dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-[0.18em] text-fog">Quoted total</dt>
          <dd>{formatInr(quotedTotal)}</dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-[0.18em] text-fog">Lead time</dt>
          <dd>{part.lead_time_days} days</dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-[0.18em] text-fog">Terms</dt>
          <dd>{part.payment_terms_default}</dd>
        </div>
      </dl>
      <p className="mt-6 max-w-sm text-sm leading-relaxed text-bone/80">{part.spec_blurb}</p>
      <p className="mt-auto pt-10 font-mono text-[11px] uppercase tracking-[0.2em] text-fog">{part.category}</p>
    </section>
  );
}
