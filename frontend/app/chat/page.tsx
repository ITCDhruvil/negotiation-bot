"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { ChatWidget } from "@/components/ChatWidget";

function ChatInner() {
  const params = useSearchParams();
  const partId = params.get("part") || "headlight-lh";
  const demo = params.get("demo") === "1";
  return <ChatWidget partId={partId} demo={demo} />;
}

export default function ChatPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-bone font-mono text-sm uppercase tracking-[0.2em] text-ink/60">
          Opening the desk…
        </div>
      }
    >
      <ChatInner />
    </Suspense>
  );
}
