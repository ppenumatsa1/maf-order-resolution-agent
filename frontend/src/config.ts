type RuntimeConfig = {
  API_BASE?: string;
};

declare global {
  interface Window {
    __APP_CONFIG__?: RuntimeConfig;
  }
}

export function getApiBase(): string {
  const runtimeBase = window.__APP_CONFIG__?.API_BASE?.trim();
  const viteBase = import.meta.env.VITE_API_BASE?.trim();
  const base = runtimeBase ?? viteBase ?? "";
  return base.replace(/\/+$/, "");
}

export function getInitialApiBase(): string {
  return getApiBase();
}
