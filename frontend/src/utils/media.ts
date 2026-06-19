import { api } from "@/api/config";

/**
 * 将本地媒体路径转为可通过 HTTP 访问的 URL（对齐 MyTodo utils/file.ts getMediaFileUrl）
 */
export function getMediaFileUrl(filePath: string): string {
  if (!filePath || typeof filePath !== "string" || filePath.trim() === "") {
    return "";
  }

  try {
    const baseURL = api.defaults.baseURL || "";
    if (!baseURL || typeof baseURL !== "string") {
      return "";
    }

    const normalized = filePath.trim().replace(/\\/g, "/");
    const path = normalized.startsWith("/") ? normalized.slice(1) : normalized;
    if (!path) {
      return "";
    }

    const encodedPath = path
      .split("/")
      .map(part => encodeURIComponent(part))
      .join("/");
    const mediaUrl = `${baseURL.replace(/\/$/, "")}/v_factory/api/media/files/${encodedPath}`;

    if (mediaUrl.includes("index.html") || mediaUrl.endsWith(".html")) {
      return "";
    }

    return mediaUrl;
  } catch {
    return "";
  }
}

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
