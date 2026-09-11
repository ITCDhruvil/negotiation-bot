"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowUp } from "lucide-react";

import { DealRail } from "@/components/DealRail";
import { InsightsPanel } from "@/components/InsightsPanel";
import { PartDossier } from "@/components/PartDossier";
import { Loader } from "@/components/prompt-kit/loader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  fetchVendorDemoTurn,
  streamChat,
  startSession,
  type ChatTurn,
  type NegotiationInsight,
  type PublicPart,
  type PublicSession,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const DEMO_MAX_TURNS = 10;
const TERMINAL = new Set(["closed", "handoff", "agreement"]);

export function ChatWidget({ partId, demo = false }: { partId: string; demo?: boolean }) {
  const [part, setPart] = useState<PublicPart | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [session, setSession] = useState<PublicSession | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [insights, setInsights] = useState<NegotiationInsight[]>([]);
  const [llmProvider, setLlmProvider] = useState<string>("");
  const [llmModel, setLlmModel] = useState<string>("");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [vendorTyping, setVendorTyping] = useState(false);
  const [demoLabel, setDemoLabel] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const demoStarted = useRef(false);
  const sessionRef = useRef<PublicSession | null>(null);
  sessionRef.current = session;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setBusy(true);
        const started = await startSession(partId);
        if (cancelled) return;
        setPart(started.listing);
        setSessionId(started.session_id);
        setLlmProvider(started.llm_provider);
        setLlmModel(started.llm_model || "");
        setSession({
          session_id: started.session_id,
          stage: started.stage,
          part_id: started.listing.part_id,
          request_id: started.listing.request_id,
          vendor_rep_name: null,
          current_bot_offer: null,
          current_vendor_offer: started.listing.vendor_quoted_unit_price,
          round_count: 0,
          handoff_flag: false,
          handoff_reason: null,
          payment_terms: null,
        });
        setTurns([{ role: "assistant", content: started.greeting }]);
        demoStarted.current = false;
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not open the desk");
      } finally {
        if (!cancelled && !demo) setBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [partId, demo]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy, vendorTyping]);

  useEffect(() => {
    if (!demo || !sessionId || !part || demoStarted.current) return;
    demoStarted.current = true;
    let cancelled = false;

    const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

    (async () => {
      let latest: PublicSession | null = sessionRef.current;
      try {
        for (let i = 0; i < DEMO_MAX_TURNS; i++) {
          if (cancelled) return;
          if (latest && TERMINAL.has(latest.stage)) break;
          setBusy(true);
          setVendorTyping(true);
          await pause(800);
          if (cancelled) return;
          const vendor = await fetchVendorDemoTurn(sessionId);
          if (cancelled) return;
          setDemoLabel(vendor.label);
          setVendorTyping(false);
          if (vendor.done || !vendor.text.trim()) break;
          setTurns((prev) => [...prev, { role: "user", content: vendor.text }, { role: "assistant", content: "" }]);
          await streamChat(sessionId, vendor.text, {
            onToken: (chunk) => {
              setTurns((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                if (last?.role === "assistant") {
                  next[next.length - 1] = { ...last, content: last.content + chunk };
                }
                return next;
              });
            },
            onSession: (nextSession) => {
              latest = nextSession;
              setSession(nextSession);
            },
            onInsights: setInsights,
            onError: setError,
          });
          if (latest && TERMINAL.has(latest.stage)) break;
          await pause(700);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Demo stopped");
      } finally {
        if (!cancelled) {
          setVendorTyping(false);
          setBusy(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [demo, sessionId, part]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!sessionId || !draft.trim() || busy) return;
    const message = draft.trim();
    setDraft("");
    setTurns((prev) => [...prev, { role: "user", content: message }, { role: "assistant", content: "" }]);
    setBusy(true);
    setError(null);
    try {
      await streamChat(sessionId, message, {
        onToken: (chunk) => {
          setTurns((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === "assistant") {
              next[next.length - 1] = { ...last, content: last.content + chunk };
            }
            return next;
          });
        },
        onSession: setSession,
        onInsights: setInsights,
        onError: setError,
      });
    } finally {
      setBusy(false);
    }
  }

  if (error && !part) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bone px-6 text-ink">
        <p>{error}. Is the backend running (BACKEND_PORT, default 8000 / fallback 8001)?</p>
      </div>
    );
  }

  if (!part) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bone font-mono text-sm uppercase tracking-[0.2em] text-ink/60">
        Opening the desk…
      </div>
    );
  }

  const closed = session?.stage === "closed" || session?.stage === "handoff";

  return (
    <div className="flex min-h-screen flex-col bg-bone md:h-screen md:flex-row md:overflow-hidden">
      <div className="flex min-h-0 flex-col md:w-[38%] md:shrink-0 md:overflow-hidden">
        <div className="min-h-0 flex-1 overflow-y-auto">
          <PartDossier part={part} />
        </div>
        <InsightsPanel insights={insights} />
      </div>
      <div className="flex min-h-0 flex-1">
        <DealRail
          vendorQuote={part.vendor_quoted_unit_price}
          currentBid={session?.current_bot_offer ?? null}
          vendorAsk={session?.current_vendor_offer ?? null}
          stage={session?.stage ?? "qualify"}
        />
        <div className="flex min-h-0 flex-1 flex-col">
          <header className="flex items-end justify-between border-b border-stitch/20 px-5 py-4">
            <div>
              <p className="font-display text-2xl leading-none text-ink">Aria</p>
              <p className="mt-1 font-mono text-[11px] uppercase tracking-[0.2em] text-stitch">
                AI procurement assistant · SKODA sourcing
                {llmProvider ? (
                  <span
                    className={cn(
                      "ml-2 tracking-[0.16em]",
                      llmProvider === "mock" ? "text-ceiling" : "text-amber"
                    )}
                  >
                    · {llmProvider === "mock" ? "stub mock" : `model ${llmModel || llmProvider}`}
                  </span>
                ) : null}
              </p>
            </div>
            <div className="text-right">
              {demo ? (
                <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-amber">
                  Demo · vendor bot{demoLabel ? ` · ${demoLabel}` : ""}
                </p>
              ) : null}
              <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink/50">
                {session?.stage.replaceAll("_", " ")}
              </p>
              <div className="mt-2 flex justify-end gap-3">
                <Link href="/" className="font-mono text-[11px] uppercase tracking-[0.16em] text-stitch hover:text-ink">
                  RFQs
                </Link>
                <Link href="/ops" className="font-mono text-[11px] uppercase tracking-[0.16em] text-amber hover:text-ink">
                  Ops
                </Link>
              </div>
            </div>
          </header>
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-6">
            {turns.map((turn, index) => {
              const waiting =
                turn.role === "assistant" &&
                !turn.content &&
                busy &&
                index === turns.length - 1;
              return (
                <article
                  key={`${turn.role}-${index}`}
                  className={cn("max-w-[36rem] text-sm leading-relaxed", turn.role === "user" ? "ml-auto" : "")}
                >
                  <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-stitch">
                    {turn.role === "user" ? "Vendor" : "Aria"}
                  </p>
                  {waiting ? (
                    <div className="mt-2">
                      <Loader variant="typing" />
                    </div>
                  ) : (
                    <p
                      className={cn(
                        "mt-1 whitespace-pre-wrap",
                        turn.role === "user" ? "bg-ink px-4 py-3 text-bone" : "text-ink"
                      )}
                    >
                      {turn.content}
                    </p>
                  )}
                </article>
              );
            })}
            {vendorTyping && (
              <article className="ml-auto max-w-[36rem] text-sm leading-relaxed">
                <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-stitch">Vendor</p>
                <div className="mt-2">
                  <Loader variant="typing" />
                </div>
              </article>
            )}
            {session?.contact_followup_required && (
              <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-amber">
                Contact follow-up required before PO
              </p>
            )}
            {session?.handoff_flag && (
              <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-ceiling">
                Sourcing handoff · {session.handoff_reason?.replaceAll("_", " ")}
              </p>
            )}
            <div ref={bottomRef} />
          </div>
          {demo ? (
            <div className="border-t border-stitch/20 bg-bone px-5 py-4">
              <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink/55">
                {busy
                  ? "Watching Aria negotiate with a vendor bot"
                  : closed
                    ? "Demo finished — this thread is with sourcing now"
                    : "Demo finished"}
              </p>
              {error ? <p className="mt-2 text-sm text-ceiling">{error}</p> : null}
            </div>
          ) : (
            <form onSubmit={onSubmit} className="flex gap-2 border-t border-stitch/20 bg-bone px-5 py-4">
              <Input
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder={closed ? "This thread is with a sourcing manager now" : "Name, unit price, or terms…"}
                disabled={busy || closed}
                aria-label="Message Aria"
              />
              <Button type="submit" size="icon" disabled={busy || closed || !draft.trim()} aria-label="Send">
                <ArrowUp className="h-4 w-4" />
              </Button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
