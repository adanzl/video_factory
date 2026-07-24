/**
 * 媒体文件 API（对齐 MyTodo media 路由）
 */
import { api } from "./config";
import type { MediaDurationResult } from "@/types/media";
import { getMediaFileUrl } from "@/utils/media";

export async function getMediaDuration(path: string): Promise<number | null> {
  if (!path?.trim()) {
    return null;
  }
  try {
    const response = await api.get<MediaDurationResult>("/v_factory/api/media/getDuration", {
      params: { path },
    });
    return typeof response.data?.duration === "number" ? response.data.duration : null;
  } catch {
    return null;
  }
}

export async function getMediaText(path: string): Promise<string | null> {
  const url = getMediaFileUrl(path);
  if (!url) {
    return null;
  }
  try {
    const response = await api.get<string>(url, { responseType: "text" });
    return typeof response.data === "string" ? response.data : null;
  } catch {
    return null;
  }
}

export async function downloadMediaFile(filePath: string, filename?: string): Promise<void> {
  const url = getMediaFileUrl(filePath);
  if (!url) {
    throw new Error("path is empty");
  }
  // 追加时间戳防止后端缓存
  const separator = url.includes("?") ? "&" : "?";
  const cacheUrl = `${url}${separator}_=${Date.now()}`;
  const response = await api.get<Blob>(cacheUrl, {
    responseType: "blob",
    // 成片可能较大，避免默认 30s 超时
    timeout: 0,
  });
  const fallbackName = filePath.trim().replace(/\\/g, "/").split("/").pop() ?? "download";
  const name = (filename?.trim() || fallbackName).replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_");
  // 强制 octet-stream，避免浏览器对 mp4/jpeg 忽略 download 文件名
  const source = response.data instanceof Blob ? response.data : new Blob([response.data]);
  const blob = new Blob([source], { type: "application/octet-stream" });
  const blobUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = blobUrl;
  anchor.download = name;
  anchor.rel = "noopener";
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  window.setTimeout(() => URL.revokeObjectURL(blobUrl), 10_000);
}

export { getMediaFileUrl, getMediaPicViewUrl, MEDIA_CROSS_ORIGIN } from "@/utils/media";
