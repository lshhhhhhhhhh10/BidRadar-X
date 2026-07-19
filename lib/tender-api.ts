export type ExtractedFields = {
  subject: string;
  region: string;
  time: string;
  frequency: string;
};

export type ProjectSummary = {
  run_id: string;
  project_id: string;
  project_code?: string;
  title: string;
  purchaser: string;
  published_at: string;
  url: string;
  source_name: string;
  budget?: number | string;
  deadline?: string;
  summary: string;
  attachments: Array<{
    attachment_id: string;
    name: string;
    url: string;
    media_type?: string | null;
    archive_status?: "available" | "failed" | "unsupported" | null;
    archive_error?: "source_has_no_pdf" | "access_denied" | "network_error" | "unsafe_url" | "too_large" | "not_pdf_response" | "write_failed" | "unknown" | null;
    local_available?: boolean;
    local_filename?: string | null;
    reveal_url?: string | null;
  }>;
  bidder_insights?: Array<{
    key: string;
    label: string;
    value: string;
    source: string;
    available: boolean;
  }>;
  contacts?: Array<{
    role: string;
    name: string;
    phone: string;
    source: string;
  }>;
  evidence_count: number;
  module_count: number;
};

export type RequirementFact = { label: string; value: string; source: string };
export type RequirementTable = { title: string; columns: string[]; rows: string[][] };
export type RequirementModule = {
  id: string;
  title: string;
  summary: string;
  facts: RequirementFact[];
  tables: RequirementTable[];
};

export type ProjectProfile = Omit<ProjectSummary, "module_count"> & {
  modules: RequirementModule[];
};

export type RunSummary = {
  task_id: string;
  run_id: string;
  query: string;
  frequency: "once" | "interval" | "daily" | "weekly";
  status: string;
  project_count: number;
};

export type ReportView = {
  status: "available" | "not_generated" | "failed" | "missing";
  delivery_type?: string | null;
  report_scope?: string | null;
  notice_count?: number;
  delivery_fingerprint?: string;
  filename?: string;
  download_url?: string;
  document_count?: number;
  documents?: ReportDocumentView[];
  error?: string;
};

export type ReportDocumentView = {
  document_id: string;
  project_id: string;
  project_title: string;
  filename: string;
  download_url: string;
  notice_count: number;
  change_type: string;
  is_new: boolean;
  generated_at?: string;
  status: "available" | "missing";
};

export type AIReportFinding = {
  text: string;
  evidence_ids: string[];
};

export type AIReportNarrative = {
  notice_id: string;
  summary: string;
  risk_points: string[];
  next_actions: string[];
  evidence_ids: string[];
};

export type AIReport = {
  status: "generated" | "not_generated";
  executive_summary?: string;
  key_findings?: AIReportFinding[];
  notice_narratives?: AIReportNarrative[];
};

export type ReportHistoryItem = {
  run_id: string;
  task_id: string;
  query: string;
  display_title?: string;
  frequency: "once" | "interval" | "daily" | "weekly";
  run_status: string;
  created_at: string;
  project_count: number;
  report: ReportView;
  ai_report: AIReport;
  projects: ProjectSummary[];
  sources: Array<{
    source_id: string;
    name: string;
    status: "success" | "failed" | "not_attempted";
    record_count: number;
    requires_login: boolean;
    attempt_count?: number;
    failure_reason?: string | null;
  }>;
};

export type LiveTaskStage = {
  id: "intent" | "expansion" | "sources" | "cleaning" | "documents";
  number: number;
  title: string;
  status: "pending" | "running" | "success" | "empty" | "error";
  summary: string;
  details: {
    fields?: Array<{ label: string; value: string }>;
    original_keywords?: string[];
    added_keywords?: string[];
    search_phrases?: string[];
    negative_terms?: string[];
    sources?: Array<{
      source_id: string;
      name: string;
      status: "pending" | "success" | "empty" | "failed";
      collected_count: number;
      relevant_count: number | null;
      requires_login: boolean;
      failure_reason?: string | null;
      attempt_count?: number;
    }>;
    counts?: Array<{ label: string; value: number }>;
    quality_issues?: string[];
    report_status?: string;
    document_count?: number;
  };
  ai: {
    status: string;
    label: string;
    model?: string | null;
    latency_ms?: number | null;
    call_count: number;
    failure_reason?: string | null;
    provider_code?: string | null;
  };
};

export type LiveTask = {
  job_id: string;
  task_id: string;
  run_id: string;
  status: "running" | "pausing" | "paused" | "completed" | "empty" | "failed";
  project_count: number;
  stages: LiveTaskStage[];
  error_message?: string | null;
  updated_at: string;
  redirect_url?: string | null;
  subscription?: SubscriptionSummary | null;
};

export type SpendBudget = {
  daily_limit: string;
  spent_today: string;
  remaining: string;
  currency: "CNY";
  enforced: boolean;
};

export type SubscriptionSummary = {
  task_id: string;
  query: string;
  frequency: "once" | "interval" | "daily" | "weekly";
  interval_minutes?: number | null;
  timezone: string;
  local_time: string;
  weekly_day?: string | null;
  next_run_at: string | null;
  status: "active" | "paused" | "completed" | "failed";
  retry_count?: number;
  max_retries?: number;
  last_error?: string | null;
  last_run_at?: string | null;
};

export type SubscriptionRunProject = {
  project_id: string;
  title: string;
  source_name: string;
  published_at?: string | null;
  url: string;
  summary: string;
};

export type SubscriptionRunSummary = {
  run_id: string;
  scheduled_for: string;
  status: "running" | "succeeded" | "failed" | "lease_expired";
  outcome: "running" | "new_content" | "no_change" | "failed";
  retry_count: number;
  started_at: string;
  completed_at?: string | null;
  error?: string | null;
  project_count: number;
  projects: SubscriptionRunProject[];
  report_available: boolean;
};

export type SubscriptionDetail = {
  subscription: SubscriptionSummary;
  runs: SubscriptionRunSummary[];
};

export type RunTaskResponse = {
  run_id: string;
  task_id: string;
  status: string;
  projects: unknown[];
  report: Record<string, unknown>;
  ai: AIStatus;
};

export type AIStatus = {
  enabled: boolean;
  configured: boolean;
  provider: string;
  model: string;
  endpoint: string;
  credential_storage: string;
  automatic?: boolean;
  fallback?: string;
  stages?: string[];
  calls?: Array<Record<string, unknown>>;
  profile_count?: number;
  candidate_count?: number;
  failover_enabled?: boolean;
  active_profile_id?: string | null;
  profiles?: AIProfile[];
};

export type AIProviderPreset = {
  id: string;
  label: string;
  default_base_url: string;
  default_model: string;
  protocol: string;
};

export type AIProfile = {
  profile_id: string;
  label: string;
  provider: string;
  base_url: string;
  model: string;
  fallback_model?: string | null;
  priority: number;
  enabled: boolean;
  configured: boolean;
  masked_key: string;
  storage: "backend_process_memory";
  created_at: string;
};

export type SourceCatalogItem = {
  id: string;
  name: string;
  category: "government" | "enterprise" | "commercial" | "overseas" | "news" | "custom";
  category_label: string;
  url: string;
  host: string;
  requires_auth: boolean;
  status: "ready" | "limited" | "needs_auth" | "restricted";
  status_label: string;
  detail: string;
  collection_mode: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";

export class TenderApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "TenderApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new TenderApiError("无法连接本地后端，请确认 FastAPI 服务已启动。", 0, "backend_unavailable");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail) && typeof detail[0]?.msg === "string"
          ? detail[0].msg.replace(/^Value error,\s*/, "")
        : typeof detail?.message === "string"
          ? detail.message
          : `本地后端请求失败（${response.status}）`;
    throw new TenderApiError(message, response.status, detail?.code);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function runTask(
  query: string,
  frequency: "once" | "interval" | "daily" | "weekly",
  overrides?: { subject?: string; region?: string },
  intervalMinutes?: number,
) {
  return request<RunTaskResponse>("/tasks/run", {
    method: "POST",
    body: JSON.stringify({ query, frequency, interval_minutes: intervalMinutes, ...overrides }),
  });
}

export async function startLiveTask(
  query: string,
  schedule: { frequency: "once" | "interval" | "daily" | "weekly"; interval_minutes?: number },
  overrides?: { subject?: string; region?: string },
) {
  return request<LiveTask>("/tasks/live", {
    method: "POST",
    body: JSON.stringify({ query, ...schedule, ...overrides }),
  });
}

export async function getLiveTask(jobId: string) {
  return request<LiveTask>(`/tasks/live/${encodeURIComponent(jobId)}`);
}

export async function pauseLiveTask(jobId: string) {
  return request<LiveTask>(`/tasks/live/${encodeURIComponent(jobId)}/pause`, {
    method: "POST",
  });
}

export async function getRun(runId: string) {
  return request<RunSummary>(`/runs/${encodeURIComponent(runId)}`);
}

export async function getRunForTask(runId: string, taskId: string) {
  const run = await getRun(runId);
  if (run.task_id !== taskId) {
    throw new TenderApiError("URL 中的 task_id 与本次运行不匹配。", 409, "run_task_mismatch");
  }
  return run;
}

export async function listProjects(runId: string) {
  return request<{ items: ProjectSummary[] }>(`/runs/${encodeURIComponent(runId)}/projects`);
}

export async function getProject(runId: string, projectId: string) {
  return request<ProjectProfile>(`/runs/${encodeURIComponent(runId)}/projects/${encodeURIComponent(projectId)}`);
}

export async function getProjectModule(runId: string, projectId: string, moduleId: string) {
  return request<{
    run_id: string;
    project_id: string;
    project_title: string;
    project_code?: string;
    module: RequirementModule;
  }>(`/runs/${encodeURIComponent(runId)}/projects/${encodeURIComponent(projectId)}/modules/${encodeURIComponent(moduleId)}`);
}

export async function getRunReport(runId: string) {
  return request<ReportView>(`/runs/${encodeURIComponent(runId)}/report`);
}

export async function listReports() {
  return request<{ items: ReportHistoryItem[] }>("/reports");
}

export async function deleteReportHistory(runId: string) {
  return request<void>(`/reports/${encodeURIComponent(runId)}`, { method: "DELETE" });
}

export async function listSubscriptions() {
  return request<{ items: SubscriptionSummary[] }>("/subscriptions");
}

export async function getSubscriptionDetail(taskId: string) {
  return request<SubscriptionDetail>(`/subscriptions/${encodeURIComponent(taskId)}/detail`);
}

export async function pauseSubscription(taskId: string) {
  return request<SubscriptionSummary>(`/subscriptions/${encodeURIComponent(taskId)}/pause`, {
    method: "POST",
  });
}

export async function resumeSubscription(taskId: string) {
  return request<SubscriptionSummary>(`/subscriptions/${encodeURIComponent(taskId)}/resume`, {
    method: "POST",
  });
}

export async function deleteSubscription(taskId: string) {
  return request<void>(`/subscriptions/${encodeURIComponent(taskId)}`, {
    method: "DELETE",
  });
}

export async function revealLocalAttachment(revealUrl: string) {
  const path = revealUrl.startsWith("/api/") ? revealUrl.slice(4) : revealUrl;
  return request<{ revealed: boolean; filename: string; folder: string }>(path, {
    method: "POST",
  });
}

export async function listSourceCatalog() {
  return request<{ items: SourceCatalogItem[] }>("/sources");
}

export async function getSpendBudget() {
  return request<SpendBudget>("/sources/budget");
}

export async function setSpendBudget(dailyLimit: string) {
  return request<SpendBudget>("/sources/budget", {
    method: "PUT",
    body: JSON.stringify({ daily_limit: dailyLimit }),
  });
}

export async function getAIStatus() {
  return request<AIStatus>("/ai/status");
}

export async function listAIProfiles() {
  return request<{
    items: AIProfile[];
    providers: AIProviderPreset[];
    storage: "backend_process_memory";
  }>("/ai/profiles");
}

export async function createAIProfile(payload: {
  label: string;
  provider: string;
  api_key: string;
  model: string;
  base_url?: string;
  fallback_model?: string;
  priority?: number;
  enabled?: boolean;
}) {
  return request<{ profile: AIProfile; ai: AIStatus }>("/ai/profiles", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAIProfile(profileId: string, enabled: boolean, priority: number) {
  return request<{ profile: AIProfile; ai: AIStatus }>(
    `/ai/profiles/${encodeURIComponent(profileId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ enabled, priority }),
    },
  );
}

export async function deleteAIProfile(profileId: string) {
  return request<void>(`/ai/profiles/${encodeURIComponent(profileId)}`, {
    method: "DELETE",
  });
}

export async function connectSourceCredential(sourceId: string, credential: string) {
  return request<{
    source_id: string;
    configured: boolean;
    masked_credential: string;
    storage: "process_memory";
    verified: boolean;
  }>(`/sources/${encodeURIComponent(sourceId)}/credential`, {
    method: "PUT",
    body: JSON.stringify({ credential }),
  });
}

export async function disconnectSourceCredential(sourceId: string) {
  return request<{ source_id: string; configured: boolean }>(
    `/sources/${encodeURIComponent(sourceId)}/credential`,
    { method: "DELETE" },
  );
}

export function resolveApiUrl(path: string): string {
  return new URL(path, `${API_BASE}/`).toString();
}

export function frequencyToApi(value: string): {
  frequency: "once" | "interval" | "daily" | "weekly";
  interval_minutes?: number;
} {
  const interval = value.match(/(?:每隔|每)\s*(\d{1,4}|[一二两三四五六七八九十]{1,4})\s*(?:分钟|分)/);
  if (interval) {
    return { frequency: "interval", interval_minutes: parseSmallChineseNumber(interval[1]) };
  }
  if (value.includes("每日") || value.includes("每天")) return { frequency: "daily" };
  if (value.includes("每周")) return { frequency: "weekly" };
  return { frequency: "once" };
}

function parseSmallChineseNumber(value: string): number {
  if (/^\d+$/.test(value)) return Number(value);
  const digits: Record<string, number> = { 一: 1, 二: 2, 两: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9 };
  if (value === "十") return 10;
  if (value.includes("十")) {
    const [left, right] = value.split("十");
    return (digits[left] ?? 1) * 10 + (digits[right] ?? 0);
  }
  return digits[value] ?? 0;
}
