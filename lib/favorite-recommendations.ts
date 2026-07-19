const STORAGE_KEY = "bidradar.favorite-recommendations.v1";
export const FAVORITE_RECOMMENDATIONS_CHANGED_EVENT = "bidradar:favorite-recommendations-changed";

export function readFavoriteRecommendations(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const value: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]");
    return Array.isArray(value)
      ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
      : [];
  } catch {
    return [];
  }
}

export function writeFavoriteRecommendations(items: string[]): string[] {
  const next = Array.from(new Set(items.map((item) => item.trim()).filter(Boolean)));
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  window.dispatchEvent(new CustomEvent(FAVORITE_RECOMMENDATIONS_CHANGED_EVENT));
  return next;
}

export function toggleFavoriteRecommendation(item: string): string[] {
  const current = readFavoriteRecommendations();
  return writeFavoriteRecommendations(
    current.includes(item)
      ? current.filter((value) => value !== item)
      : [item, ...current],
  );
}

export function removeFavoriteRecommendation(item: string): string[] {
  return writeFavoriteRecommendations(
    readFavoriteRecommendations().filter((value) => value !== item),
  );
}
