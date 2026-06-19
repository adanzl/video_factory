import type { Router } from "vue-router";

const CHUNK_ERROR_RE =
  /Failed to fetch dynamically imported module|Loading chunk|Importing a module script failed/;

export function setupChunkReloadGuard(router: Router): void {
  router.onError((error, to) => {
    const msg = String((error as Error)?.message ?? error);
    if (!CHUNK_ERROR_RE.test(msg)) return;

    const key = `chunk-reload:${to.fullPath}`;
    if (!sessionStorage.getItem(key)) {
      sessionStorage.setItem(key, "1");
      const base = window.location.pathname + window.location.search;
      window.location.assign(`${base}#${to.fullPath}`);
      return;
    }
    sessionStorage.removeItem(key);
  });
}
