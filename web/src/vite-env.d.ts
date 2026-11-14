/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_ADAPTER?: string;
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_DEV_PROXY_TARGET?: string;
  readonly VITE_DEVCONSOLE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
