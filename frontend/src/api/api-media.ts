/**
 * 媒体文件 API（对齐 MyTodo media 路由）
 */
import { api } from "./config";
import type { MediaDurationResult } from "@/types/media";
import { normalizeMediaServePath } from "@/utils/media";

export async function getMediaDuration(path: string): Promise<number | null> {
  if (!path?.trim()) {
    return null;
  }
  try {
    const response = await api.get<MediaDurationResult>("/v_factory/api/media/getDuration", {
      params: { path: normalizeMediaServePath(path) },
    });
    return typeof response.data?.duration === "number" ? response.data.duration : null;
  } catch {
    return null;
  }
}

export async function getMediaText(path: string): Promise<string | null> {
  const normalized = normalizeMediaServePath(path ?? "");
  if (!normalized) {
    return null;
  }
  const encodedPath = normalized
    .split("/")
    .map(part => encodeURIComponent(part))
    .join("/");
  try {
    const response = await api.get<string>(`/v_factory/api/media/files/${encodedPath}`, {
      responseType: "text",
    });
    return typeof response.data === "string" ? response.data : null;
  } catch {
    return null;
  }
}

export async function downloadMediaFile(filePath: string, filename?: string): Promise<void> {
  const path = normalizeMediaServePath(filePath ?? "");
  if (!path) {
    throw new Error("path is empty");
  }
  const encodedPath = path
    .split("/")
    .map(part => encodeURIComponent(part))
    .join("/");
  const response = await api.get<Blob>(`/v_factory/api/media/files/${encodedPath}`, {
    responseType: "blob",
  });
  const name = filename ?? path.split("/").pop() ?? "download";
  const blobUrl = URL.createObjectURL(response.data);
  const anchor = document.createElement("a");
  anchor.href = blobUrl;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(blobUrl);
}

export { getMediaFileUrl } from "@/utils/media";
