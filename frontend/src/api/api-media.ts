/**
 * 媒体文件 API（对齐 MyTodo media 路由）
 */
import { api } from "./config";
import type { MediaDurationResult } from "@/types/media";

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
  const normalized = path?.trim().replace(/\\/g, "/");
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

export { getMediaFileUrl } from "@/utils/media";
