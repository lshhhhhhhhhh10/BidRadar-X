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
  budget?: number;
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

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `本地后端请求失败（${response.status}）`);
  }
  return response.json() as Promise<T>;
}

export async function runTask(query: string, frequency: "once" | "daily" | "weekly") {
  return request<{ run_id: string; task_id: string; projects: unknown[] }>("/tasks/run", {
    method: "POST",
    body: JSON.stringify({ query, frequency }),
  });
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

export function frequencyToApi(value: string): "once" | "daily" | "weekly" {
  if (value.includes("每日")) return "daily";
  if (value.includes("每周")) return "weekly";
  return "once";
}

export function saveRunContext(runId: string, query: string, fields: ExtractedFields) {
  sessionStorage.setItem("tender-active-run", runId);
  sessionStorage.setItem("tender-query", query);
  sessionStorage.setItem("tender-fields", JSON.stringify(fields));
}

export function getRunIdFromLocation(): string {
  const queryRun = new URLSearchParams(window.location.search).get("run");
  return queryRun || sessionStorage.getItem("tender-active-run") || "";
}
