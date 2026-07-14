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
  frequency: "once" | "daily" | "weekly";
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
  error?: string;
};

export type ReportHistoryItem = {
  run_id: string;
  task_id: string;
  query: string;
  frequency: "once" | "daily" | "weekly";
  run_status: string;
  created_at: string;
  project_count: number;
  report: ReportView;
};

export type RunTaskResponse = {
  run_id: string;
  task_id: string;
  status: string;
  projects: unknown[];
  report: Record<string, unknown>;
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
        : typeof detail?.message === "string"
          ? detail.message
          : `本地后端请求失败（${response.status}）`;
    throw new TenderApiError(message, response.status, detail?.code);
  }
  return response.json() as Promise<T>;
}

export async function runTask(query: string, frequency: "once" | "daily" | "weekly") {
  return request<RunTaskResponse>("/tasks/run", {
    method: "POST",
    body: JSON.stringify({ query, frequency }),
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

export function resolveApiUrl(path: string): string {
  return new URL(path, `${API_BASE}/`).toString();
}

export function frequencyToApi(value: string): "once" | "daily" | "weekly" {
  if (value.includes("每日")) return "daily";
  if (value.includes("每周")) return "weekly";
  return "once";
}
