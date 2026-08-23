export type Theme = "dark" | "light";

const STORAGE_KEY = "agenthub.theme";
export const THEME_CHANGED_EVENT = "agenthub:theme-changed";

export function getStoredTheme(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

export function storeTheme(theme: Theme): void {
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // localStorage 不可用时仅本次会话生效
  }
}

export function toggleTheme(current: Theme): Theme {
  const next: Theme = current === "dark" ? "light" : "dark";
  storeTheme(next);
  window.dispatchEvent(
    new CustomEvent<Theme>(THEME_CHANGED_EVENT, { detail: next }),
  );
  return next;
}
