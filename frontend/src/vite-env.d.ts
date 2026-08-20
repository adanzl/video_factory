/// <reference types="vite/client" />
/// <reference types="../../auto-imports.d.ts" />

import type {} from "axios";

declare global {
  interface ImportMetaEnv {
    readonly VITE_API_BASE_URL: string;
  }

  interface ImportMeta {
    readonly env: ImportMetaEnv;
  }
}

declare module "axios" {
  export interface AxiosRequestConfig {
    skipErrorNotice?: boolean;
  }
}

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>;
  export default component;
}
