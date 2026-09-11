export type PublicPart = {
  part_id: string;
  part_name: string;
  category: string;
  vendor_id: string;
  vendor_name: string;
  vendor_quoted_unit_price: number;
  quantity: number;
  moq: number | null;
  lead_time_days: number;
  payment_terms_default: string;
  spec_blurb: string;
  request_id: string;
  request_title: string;
  plant: string;
};

export type CatalogRequest = {
  request_id: string;
  title: string;
  plant: string;
  needed_by: string | null;
  parts: PublicPart[];
};

export type PublicSession = {
  session_id: string;
  stage: string;
  part_id: string;
  request_id: string;
  vendor_rep_name: string | null;
  current_bot_offer: number | null;
  current_vendor_offer: number | null;
  round_count: number;
  handoff_flag: boolean;
  handoff_reason: string | null;
  payment_terms: string | null;
  current_lead_time_days?: number | null;
  current_moq?: number | null;
  contact_followup_required?: boolean;
};

export type ChatTurn = {
  role: "user" | "assistant";
  content: string;
};

export type NegotiationInsight = {
  round_number: number;
  intent: string;
  sentiment: string;
  signal_confidence: string;
  tactic: string | null;
  situation?: string | null;
  reasoning: string | null;
  extracted_facts: Record<string, unknown>;
  timestamp: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/backend";

export async function fetchCatalog(): Promise<{ company: string; requests: CatalogRequest[] }> {
  const res = await fetch(`${API_BASE}/api/catalog`, { cache: "no-store" });
  if (!res.ok) throw new Error("Could not load catalog");
  return res.json();
}

export type RfqAlternateDraft = {
  vendor_id?: string;
  vendor_name: string;
  unit_price: number | null;
};

export type RfqPartDraft = {
  part_id?: string;
  part_name: string;
  category: string;
  vendor_id: string;
  vendor_name: string;
  vendor_quoted_unit_price: number | null;
  quantity: number | null;
  moq: number | null;
  target_unit_price: number | null;
  max_acceptable_unit_price: number | null;
  lead_time_days: number | null;
  payment_terms_default: string;
  spec_blurb: string;
  target_lead_time_days: number | null;
  max_acceptable_lead_time_days: number | null;
  max_acceptable_moq: number | null;
  preferred_payment_terms: string;
  fastest_payment_terms: string;
  min_warranty_months: number | null;
  alternate_vendor_quotes: RfqAlternateDraft[];
  missing: string[];
};

export type RfqDraft = {
  request_id: string;
  title: string;
  plant: string;
  needed_by: string | null;
  parts: RfqPartDraft[];
  warnings: string[];
  source: string;
  filename: string | null;
};

async function readApiError(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => null);
  if (body && typeof body.detail === "string") return body.detail;
  return fallback;
}

export async function parseRfqDocument(file: File, pastedText = ""): Promise<RfqDraft> {
  const data = new FormData();
  data.append("file", file);
  if (pastedText.trim()) data.append("text", pastedText);
  const res = await fetch(`${API_BASE}/api/rfq/parse`, { method: "POST", body: data });
  if (!res.ok) throw new Error(await readApiError(res, "Could not read that document"));
  return res.json();
}

export async function parseRfqText(text: string): Promise<RfqDraft> {
  const res = await fetch(`${API_BASE}/api/rfq/parse-text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Could not read that text"));
  return res.json();
}

export async function createRfq(payload: {
  request_id?: string;
  title: string;
  plant: string;
  needed_by?: string | null;
  parts: Array<Omit<RfqPartDraft, "missing"> & { missing?: string[] }>;
}): Promise<{ request_id: string; title: string; parts: PublicPart[] }> {
  const res = await fetch(`${API_BASE}/api/rfq`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Could not create the RFQ"));
  return res.json();
}

export async function startSession(partId: string): Promise<{
  session_id: string;
  stage: string;
  listing: PublicPart;
  greeting: string;
  llm_provider: string;
  llm_model?: string;
}> {
  const res = await fetch(`${API_BASE}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ part_id: partId }),
  });
  if (!res.ok) throw new Error("Could not start session");
  return res.json();
}

export type StreamHandlers = {
  onToken: (chunk: string) => void;
  onSession: (session: PublicSession) => void;
  onPrice?: (amount: number) => void;
  onInsights?: (insights: NegotiationInsight[]) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
};

export async function fetchVendorDemoTurn(
  sessionId: string,
  persona?: string
): Promise<{ text: string; persona: string | null; label: string | null; done: boolean }> {
  const res = await fetch(`${API_BASE}/api/demo/vendor-turn`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, persona: persona || null }),
  });
  if (!res.ok) throw new Error("Vendor bot did not reply");
  return res.json();
}

export async function streamChat(sessionId: string, message: string, handlers: StreamHandlers) {
  const res = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  if (!res.ok || !res.body) {
    handlers.onError?.("The sourcing desk is not reachable right now.");
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.split("\n").find((entry) => entry.startsWith("data: "));
      if (!line) continue;
      const payload = JSON.parse(line.slice(6));
      if (payload.type === "token") handlers.onToken(payload.content);
      if (payload.type === "session") handlers.onSession(payload.session);
      if (payload.type === "insights") handlers.onInsights?.(payload.insights);
      if (payload.type === "price") handlers.onPrice?.(payload.amount);
      if (payload.type === "error") handlers.onError?.(payload.message);
      if (payload.type === "done") handlers.onDone?.();
    }
  }
}
