/**
 * 素材片段聚合搜索 API（不入库）
 */
import { api } from "./config";
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
