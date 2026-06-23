/** 素材片段聚合搜索类型 */

export type ClipProviderName = "pexels" | "pixabay" | "nasa";

export type ClipSearchLanguage = "" | "zh" | "en";

export type ClipSearchMode = "original" | "ai";

export interface ClipProviderStatus {
  provider: ClipProviderName;
  available: boolean;
  requires_api_key: boolean;
  reason?: string | null;
}

export interface StockClip {
  id: string;
  provider: ClipProviderName;
  title: string;
  preview_url: string;
  video_url: string;
  page_url: string;
  license: string;
  duration_sec?: number | null;
  width?: number | null;
  height?: number | null;
  author?: string | null;
}

export interface ClipProviderSearchMeta {
  provider: ClipProviderName;
  status: "ok" | "skipped" | "error";
  count: number;
  reason?: string | null;
}

export interface ClipSearchResult {
  query: string;
  search_mode?: ClipSearchMode;
  total: number;
  clips: StockClip[];
  providers: ClipProviderSearchMeta[];
  resolved_query?: string | null;
}

export interface SearchClipsParams {
  q: string;
  per_page?: number;
  providers?: ClipProviderName[];
  orientation?: "portrait" | "landscape" | "square";
  language?: ClipSearchLanguage;
  search_mode?: ClipSearchMode;
}
