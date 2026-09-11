"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/ops", label: "Overview" },
  { href: "/ops/data", label: "Data" },
  { href: "/ops/logs", label: "Logs" },
  { href: "/ops/finetune", label: "Fine-tune" },
];

export function OpsShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-bone text-ink">
      <header className="border-b border-stitch/25 px-6 py-5 md:px-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.28em] text-stitch">
              SKODA sourcing · ops
            </p>
            <h1 className="mt-2 font-display text-4xl leading-none md:text-5xl">Aria desk.</h1>
          </div>
          <Link
            href="/"
            className="inline-flex h-11 items-center justify-center border border-stitch/40 px-4 text-sm text-ink hover:bg-amber/15"
          >
            Open RFQs
          </Link>
        </div>
        <nav className="mt-6 flex flex-wrap gap-2" aria-label="Ops dashboards">
          {LINKS.map((link) => {
            const active = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "inline-flex h-10 items-center px-4 font-mono text-[11px] uppercase tracking-[0.18em]",
                  active ? "bg-ink text-bone" : "border border-stitch/30 text-ink hover:bg-amber/15"
                )}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
      </header>
      <div className="px-6 py-8 md:px-10">{children}</div>
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "default" | "deal" | "ceiling" | "amber";
}) {
  const color =
    tone === "deal" ? "text-deal" : tone === "ceiling" ? "text-ceiling" : tone === "amber" ? "text-amber" : "text-ink";
  return (
    <div className="border border-stitch/25 bg-bone p-4">
      <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-stitch">{label}</p>
      <p className={cn("mt-2 font-display text-3xl leading-none", color)}>{value}</p>
      {hint ? <p className="mt-2 text-sm text-ink/60">{hint}</p> : null}
    </div>
  );
}

export function OpsButton({
  children,
  onClick,
  disabled,
  variant = "solid",
  danger = false,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "solid" | "ghost";
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "inline-flex h-11 items-center justify-center px-4 text-sm disabled:opacity-40",
        danger
          ? "border border-ceiling bg-transparent text-ceiling hover:bg-ceiling/10"
          : variant === "solid"
            ? "bg-ink text-bone hover:bg-pit"
            : "border border-amber bg-transparent text-ink hover:bg-amber/15"
      )}
    >
      {children}
    </button>
  );
}

export function usePagedList<T>(items: T[], pageSize = 8, resetKey?: string | number) {
  const [page, setPage] = useState(1);
  const pages = Math.max(1, Math.ceil(items.length / pageSize) || 1);
  useEffect(() => {
    setPage(1);
  }, [resetKey, pageSize]);
  useEffect(() => {
    if (page > pages) setPage(pages);
  }, [page, pages]);
  const current = Math.min(page, pages);
  const slice = useMemo(() => {
    const start = (current - 1) * pageSize;
    return items.slice(start, start + pageSize);
  }, [current, items, pageSize]);
  return { page: current, pages, total: items.length, slice, setPage, pageSize };
}

export function Pager({
  page,
  pages,
  total,
  pageSize,
  onPage,
  noun = "rows",
}: {
  page: number;
  pages: number;
  total: number;
  pageSize: number;
  onPage: (next: number) => void;
  noun?: string;
}) {
  if (total <= pageSize) return null;
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
      <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink/50">
        {start}–{end} of {total} {noun}
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
          className="inline-flex h-9 items-center px-3 font-mono text-[11px] uppercase tracking-[0.16em] border border-stitch/30 text-ink hover:bg-amber/15 disabled:opacity-40"
        >
          Prev
        </button>
        <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-stitch">
          {page} / {pages}
        </span>
        <button
          type="button"
          disabled={page >= pages}
          onClick={() => onPage(page + 1)}
          className="inline-flex h-9 items-center px-3 font-mono text-[11px] uppercase tracking-[0.16em] border border-stitch/30 text-ink hover:bg-amber/15 disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  );
}
