const STORAGE_KEY = "bidradar.starred-subscriptions.v1";
export const STARRED_SUBSCRIPTIONS_CHANGED_EVENT = "bidradar:starred-subscriptions-changed";


export function readStarredSubscriptionIds(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const value = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]");
    return Array.isArray(value)
      ? [...new Set(value.filter((item): item is string => typeof item === "string" && item.length > 0))]
      : [];
  } catch {
    return [];
  }
}


export function toggleStarredSubscription(taskId: string): string[] {
  const current = readStarredSubscriptionIds();
  const next = current.includes(taskId)
    ? current.filter((item) => item !== taskId)
    : [taskId, ...current];
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  window.dispatchEvent(new CustomEvent(STARRED_SUBSCRIPTIONS_CHANGED_EVENT));
  return next;
}


export function removeStarredSubscription(taskId: string): string[] {
  const next = readStarredSubscriptionIds().filter((item) => item !== taskId);
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  window.dispatchEvent(new CustomEvent(STARRED_SUBSCRIPTIONS_CHANGED_EVENT));
  return next;
}
