/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DATA_MODE?: string;
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_DEV_PROXY_TARGET?: string;
  readonly VITE_EXPERIMENT_POLL_MS?: string;
  readonly VITE_RUN_POLL_MS?: string;
  readonly VITE_REQUEST_TIMEOUT_MS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
