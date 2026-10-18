/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API origin; empty in dev (Vite proxies /api to the local backend). */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare module "*.ftl?raw" {
  const source: string;
  export default source;
}
