/**
 * 媒体文件 API（仿 MyTodo media 路由）
 */
import { api, getApiUrl } from "./config";
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

/** 将本地媒体路径转为可通过 HTTP 访问的 URL */
export function getMediaFileUrl(filePath: string): string {
  const trimmed = filePath?.trim();
  if (!trimmed) {
    return "";
  }

  const baseURL = getApiUrl();
  if (!baseURL) {
    return "";
  }

  const normalized = trimmed.replace(/\\/g, "/").replace(/^\/+/, "");
  const encodedPath = normalized
    .split("/")
    .map(part => encodeURIComponent(part))
    .join("/");

  return `${baseURL}/v_factory/api/media/files/${encodedPath}`;
}
