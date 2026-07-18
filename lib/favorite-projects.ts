export type FavoriteProject = {
  id: string;
  runId: string;
  title: string;
  region: string;
  sourceName: string;
  addedAt: string;
};

const STORAGE_KEY = "bidradar.favorite-projects.v1";
export const FAVORITES_CHANGED_EVENT = "bidradar:favorites-changed";

export function readFavoriteProjects(): FavoriteProject[] {
  if (typeof window === "undefined") return [];
  try {
    const value = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]");
    return Array.isArray(value) ? value.filter(isFavoriteProject) : [];
  } catch {
    return [];
  }
}

export function isFavoriteProject(project: unknown): project is FavoriteProject {
  if (!project || typeof project !== "object") return false;
  const value = project as Partial<FavoriteProject>;
  return typeof value.id === "string" && typeof value.title === "string" && typeof value.runId === "string";
}

export function toggleFavoriteProject(project: FavoriteProject): FavoriteProject[] {
  const current = readFavoriteProjects();
  const next = current.some((item) => item.id === project.id && item.runId === project.runId)
    ? current.filter((item) => item.id !== project.id || item.runId !== project.runId)
    : [project, ...current];
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  window.dispatchEvent(new CustomEvent(FAVORITES_CHANGED_EVENT));
  return next;
}

export function removeFavoriteProject(project: Pick<FavoriteProject, "id" | "runId">): FavoriteProject[] {
  const next = readFavoriteProjects().filter(
    (item) => item.id !== project.id || item.runId !== project.runId,
  );
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  window.dispatchEvent(new CustomEvent(FAVORITES_CHANGED_EVENT));
  return next;
}
