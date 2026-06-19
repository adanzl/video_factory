export { getMediaDuration, getMediaFileUrl } from "@/api/api-media";

/** 格式化媒体时长（秒 → mm:ss） */
export function formatMediaDuration(seconds?: number | null): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) {
    return "-";
  }
  const total = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}
