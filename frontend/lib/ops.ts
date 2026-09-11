const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/backend";

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `Request failed: ${path}`);
  }
  return res.json();
}

async function postJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: "POST", cache: "no-store" });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `Request failed: ${path}`);
  }
  return res.json();
}

async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(friendlyError(detail) || `Request failed: ${path}`);
  }
  return res.json();
}

function friendlyError(raw: string) {
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    return raw;
  }
  return raw;
}

export type HealthPayload = {
  ok: boolean;
  provider: string | null;
  is_mock: boolean;
  chat_model: string | null;
  reasoning_model: string | null;
  company: string;
  port: number;
  finetune_auto?: boolean;
};

export type SessionRow = {
  session_id: string;
  part_id: string | null;
  stage: string | null;
  updated_at: string | null;
  round_count?: number | null;
  handoff_flag?: boolean;
  handoff_reason?: string | null;
  current_bot_offer?: number | null;
  current_vendor_offer?: number | null;
  vendor_company?: string | null;
  vendor_rep_name?: string | null;
};

export type OpsOverview = {
  health: HealthPayload;
  counts: {
    sessions: number;
    turns: number;
    insights: number;
    lessons: number;
    labels: number;
    jobs: number;
    catalog_parts: number;
  };
  sessions: SessionRow[];
  audit_db: string;
  pipeline: {
    ready: boolean;
    auto: boolean;
    train_examples: number | null;
    min_examples: number | null;
    label_counts: Record<string, number> | null;
    active_chat_model: string | null;
    open_job: Record<string, unknown> | null;
    guidance?: { band: string; note: string };
  };
};

export type AuditTurn = {
  id?: number;
  session_id: string;
  role: string;
  content: string;
  validated_price?: number | null;
  tactic?: string | null;
  situation?: string | null;
  reasoning?: string | null;
  interpreted_intent?: string | null;
  stage?: string | null;
  model?: string | null;
  created_at?: string | null;
};

export type LessonRow = {
  id: string;
  session_id?: string | null;
  part_id?: string | null;
  part_name?: string | null;
  vendor_name?: string | null;
  situation?: string | null;
  outcome?: string | null;
  handoff_reason?: string | null;
  final_price?: number | null;
  opening_quote?: number | null;
  rounds?: number | null;
  tactics?: string[] | string | null;
  note?: string | null;
  created_at?: string | null;
};

export type LabelRow = {
  session_id: string;
  quality: string;
  outcome?: string | null;
  reasons?: string[] | string | null;
  situations?: string[] | string | null;
  tactics?: string[] | string | null;
  voice_examples?: number | null;
  brain_examples?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type FineTuneGuidance = {
  band: string;
  openai_floor: number;
  note: string;
  have?: number;
  need?: number;
};

export type FineTuneConfig = {
  auto: boolean;
  base_model: string;
  min_examples: number;
  suffix: string;
  n_epochs: number | "auto" | null;
  auto_promote: boolean;
  tick_seconds: number;
  allowed_base_models: string[];
  openai_floor: number;
  source: string;
  updated_at?: string | null;
  guidance?: FineTuneGuidance;
};

export type FineTuneStatus = {
  auto: boolean;
  base_model: string;
  min_examples: number;
  config?: FineTuneConfig;
  guidance?: FineTuneGuidance;
  label_counts: Record<string, number>;
  labels: LabelRow[];
  preview: {
    closed_sessions?: number;
    train_sessions?: number;
    voice_examples?: number;
    train_examples?: number;
    valid_examples?: number;
    brain_examples?: number;
    skipped_sessions?: number;
    min_examples?: number;
    base_model?: string;
    auto?: boolean;
    ready?: boolean;
    note?: string;
    voice_path?: string;
    valid_path?: string;
    brain_path?: string;
  };
  ready: boolean;
  fingerprint: string;
  open_job: Record<string, unknown> | null;
  last_job: Record<string, unknown> | null;
  active_chat_model: string;
  promoted: Record<string, unknown> | null;
  jobs: Record<string, unknown>[];
  note?: string;
};

export type SessionLog = {
  session_id: string;
  turns: AuditTurn[];
  insights: Record<string, unknown>[];
  lessons: LessonRow[];
  label: LabelRow | null;
  stage?: string;
  part_id?: string;
  handoff_reason?: string | null;
  round_count?: number;
  current_bot_offer?: number | null;
  current_vendor_offer?: number | null;
};

export function fetchHealth() {
  return getJson<HealthPayload>("/health");
}

export function fetchOverview() {
  return getJson<OpsOverview>("/api/ops/overview");
}

export function fetchLoggedSessions() {
  return getJson<{ sessions: SessionRow[] }>("/api/logs/sessions");
}

export function fetchRecentTurns() {
  return getJson<{ turns: AuditTurn[] }>("/api/logs/recent");
}

export function fetchLessons() {
  return getJson<{ lessons: LessonRow[] }>("/api/lessons");
}

export function fetchLabels(quality?: string) {
  const suffix = quality ? `?quality=${encodeURIComponent(quality)}` : "";
  return getJson<{ labels: LabelRow[] }>(`/api/labels${suffix}`);
}

export function fetchSessionLog(sessionId: string) {
  return getJson<SessionLog>(`/api/sessions/${encodeURIComponent(sessionId)}/log`);
}

export function fetchFineTuneStatus() {
  return getJson<FineTuneStatus>("/api/finetune/status");
}

export function fetchFineTunePreview() {
  return getJson<FineTuneStatus["preview"]>("/api/finetune/preview");
}

export function postFineTuneTick() {
  return postJson<Record<string, unknown>>("/api/finetune/tick");
}

export function postFineTuneExport() {
  return postJson<FineTuneStatus["preview"]>("/api/finetune/export");
}

export function postFineTuneSubmit() {
  return postJson<Record<string, unknown>>("/api/finetune/submit");
}

export function patchFineTuneSettings(body: Partial<FineTuneConfig> & { n_epochs?: number | "auto" | null }) {
  return patchJson<FineTuneConfig>("/api/finetune/settings", body);
}

export function asList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String);
  if (typeof value === "string" && value.trim()) {
    try {
      const parsed = JSON.parse(value);
      if (Array.isArray(parsed)) return parsed.map(String);
    } catch {
      return [value];
    }
  }
  return [];
}
