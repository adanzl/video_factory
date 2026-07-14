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
  const response = await api.get<Blob>(cacheUrl, { responseType: "blob" });
  const name = filename ?? filePath.trim().replace(/\\/g, "/").split("/").pop() ?? "download";
  const blobUrl = URL.createObjectURL(response.data);
  const anchor = document.createElement("a");
  anchor.href = blobUrl;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(blobUrl);
}

export { getMediaFileUrl, getMediaPicViewUrl, MEDIA_CROSS_ORIGIN } from "@/utils/media";
