/**
 * 素材片段聚合搜索 API（不入库）
 */
import { api, getApiUrl } from "./config";
import type {
  ClipProviderStatus,
  ClipSearchResult,
  ClipProviderName,
  SearchClipsParams,
} from "@/types/clipSearch";

export async function listClipSources(): Promise<ClipProviderStatus[]> {
  const response = await api.get<ClipProviderStatus[]>("/v_factory/api/clips/sources");
  return Array.isArray(response.data) ? response.data : [];
}

export async function searchClips(params: SearchClipsParams): Promise<ClipSearchResult> {
  const response = await api.get<ClipSearchResult>("/v_factory/api/clips/search", {
    params: {
      q: params.q,
      per_page: params.per_page ?? 24,
      providers: params.providers?.length ? params.providers.join(",") : undefined,
      orientation: params.orientation,
    },
    timeout: 60000,
  });
  return response.data;
}

export const CLIP_PROVIDER_LABELS: Record<ClipProviderName, string> = {
  pexels: "Pexels",
  pixabay: "Pixabay",
  nasa: "NASA",
};

/** poster 必须是图片；若后端误传 mp4 则忽略 */
export function clipPosterUrl(previewUrl?: string): string | undefined {
  const trimmed = previewUrl?.trim();
  if (!trimmed) {
    return undefined;
  }
  if (/\.(mp4|webm|m3u8)(\?|#|$)/i.test(trimmed)) {
    return undefined;
  }
  return trimmed;
}

/** 经后端校验后播放；Pexels/Pixabay 等 CDN 直连，避免 gevent 代理大文件 */
const DIRECT_PLAY_HOSTS = [
  "videos.pexels.com",
  "player.vimeo.com",
  "cdn.pixabay.com",
  "images-assets.nasa.gov",
];

export function clipPreviewUrl(remoteUrl: string): string {
  const trimmed = remoteUrl?.trim();
  if (!trimmed) {
    return "";
  }
  try {
    const host = new URL(trimmed).hostname.toLowerCase();
    if (DIRECT_PLAY_HOSTS.some(h => host === h || host.endsWith(`.${h}`))) {
      return trimmed;
    }
  } catch {
    // 非法 URL 仍走代理校验
  }
  const base = getApiUrl();
  return `${base}/v_factory/api/clips/preview?url=${encodeURIComponent(trimmed)}`;
}
