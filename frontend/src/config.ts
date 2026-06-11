type RuntimeConfig = {
  API_BASE?: string;
};

declare global {
  interface Window {
    __APP_CONFIG__?: RuntimeConfig;
  }
}

export function getApiBase(): string {
  return (
    window.__APP_CONFIG__?.API_BASE ??
    import.meta.env.VITE_API_BASE ??
    "http://localhost:8000"
  );
}
