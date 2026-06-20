import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";

dayjs.extend(utc);

/** SQLite datetime('now') 为 UTC，格式如 2026-06-20 19:01:33（无 Z 后缀） */
const SQLITE_UTC_RE = /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}$/;

export function formatDateTime(value?: string | number | Date | null): string {
  if (!value) return "-";
  if (typeof value === "string") {
    const normalized = value.trim();
    if (SQLITE_UTC_RE.test(normalized)) {
      return dayjs.utc(normalized).local().format("YYYY-MM-DD HH:mm:ss");
    }
  }
  return dayjs(value).format("YYYY-MM-DD HH:mm:ss");
}
