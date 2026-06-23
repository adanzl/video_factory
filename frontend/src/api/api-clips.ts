/**
 * 素材片段聚合搜索 API
 */
import { api, getApiUrl } from "./config";
import type { JobSegment } from "@/types/jobs";
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
      language: params.language || undefined,
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

/** 经后端同源代理播放，避免跨域 CDN 在 Firefox 等浏览器报 MIME 错误 */
export function clipPreviewUrl(remoteUrl: string): string {
  const trimmed = remoteUrl?.trim();
  if (!trimmed) {
    return "";
  }
  const base = getApiUrl();
  return `${base}/v_factory/api/clips/preview?url=${encodeURIComponent(trimmed)}`;
}

export async function importClipToSegment(payload: {
  jobId: number;
  segmentIndex: number;
  videoUrl: string;
}): Promise<JobSegment> {
  const response = await api.post<JobSegment>("/v_factory/api/clips/import-segment", {
    id: payload.jobId,
    segment_index: payload.segmentIndex,
    video_url: payload.videoUrl,
  });
  return response.data;
}
