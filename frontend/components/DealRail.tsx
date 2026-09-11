import { formatInr } from "@/lib/utils";

type DealRailProps = {
  vendorQuote: number;
  currentBid: number | null;
  vendorAsk: number | null;
  stage: string;
};

export function DealRail({ vendorQuote, currentBid, vendorAsk, stage }: DealRailProps) {
  const top = vendorQuote;
  const bid = currentBid ?? Math.round(vendorQuote * 0.85);
  const bidPct = top > 0 ? Math.min(96, Math.max(4, (bid / top) * 100)) : 8;
  const vendorPct =
    vendorAsk != null && top > 0 ? Math.min(96, Math.max(4, (vendorAsk / top) * 100)) : null;
  const negotiating = ["negotiate", "open_offer", "agreement", "closed"].includes(stage);

  return (
    <aside className="hidden h-full w-16 shrink-0 flex-col items-center py-6 md:flex" aria-label="Bid rail">
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-stitch">Bid</p>
      <div className="relative mt-4 h-full w-[2px] bg-fog">
        <span className="absolute left-3 top-0 font-mono text-[9px] uppercase tracking-wider text-fog">Ask</span>
        {negotiating && (
          <span
            className="absolute left-1/2 h-3 w-3 -translate-x-1/2 rounded-full bg-amber shadow-[0_0_0_4px_rgba(224,154,61,0.25)]"
            style={{ top: `${100 - bidPct}%` }}
            title={`Our bid ${formatInr(bid)}`}
          />
        )}
        {vendorPct != null && (
          <span
            className="absolute left-1/2 h-2 w-2 -translate-x-1/2 rounded-full bg-ink"
            style={{ top: `${100 - vendorPct}%` }}
            title={`Vendor ${formatInr(vendorAsk ?? 0)}`}
          />
        )}
      </div>
      <p className="mt-4 font-mono text-[10px] text-ink/50">{formatInr(bid)}</p>
    </aside>
  );
}
