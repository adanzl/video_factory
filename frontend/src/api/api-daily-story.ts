import { api } from "./config";
import type { ListResponse } from "@/types";

export interface DialogueLine {
  speaker: string;
  line: string;
}

export interface StoryQuality {
  grade: "好" | "中" | "偏弱" | string;
  score: number;
  summary: string;
  reasons?: string[];
}

export interface StoryContent {
  scene_title: string;
  setting: string;
  /** 内容标签：2–8 字，如「饭前偷吃」，防重复（旧稿可能缺失） */
  key?: string;
  /** 单冲突摘要：谁 vs 谁争什么（旧稿可能缺失） */
  conflict_core?: string;
  dialogue: DialogueLine[];
  punchline_explain: string;
  discovery_opening?: DialogueLine[];
  quality?: StoryQuality;
}

export interface DailyStoryRecord {
  id: number;
  theme: string;
  story: StoryContent;
  /** 内容标签，表列权威；与 story.key 同步 */
  key: string | null;
  /** 矛盾类型代码 A–G，来自笑点解析 */
  story_type: string | null;
  job_id: number | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export type DailyStoryListResponse = ListResponse<DailyStoryRecord>;

/** 与后端 STORY_TYPE_LABELS 一致 */
export const DAILY_STORY_TYPE_LABELS: Record<string, string> = {
  A: "权威翻车",
  B: "结盟翻车",
  C: "公平执念",
  D: "字面执行",
  E: "妈妈破功",
  G: "嘴硬心软",
};

/** 如 A权威翻车；无有效代码时返回 "-" */
export function formatDailyStoryType(code: string | null | undefined): string {
  const c = (code ?? "").trim().toUpperCase();
  const label = DAILY_STORY_TYPE_LABELS[c];
  if (!label) return "-";
  return `${c}${label}`;
}

/** 多个类型用 / 连接 */
export function formatDailyStoryTypes(codes: string[] | null | undefined): string {
  const parts = (codes ?? [])
    .map((c) => formatDailyStoryType(c))
    .filter((s) => s !== "-");
  return parts.length ? parts.join(" / ") : "-";
}

export const DAILY_STORY_TYPE_OPTIONS = (["A", "B", "C", "D", "E", "G"] as const).map(
  (code) => ({
    value: code,
    label: formatDailyStoryType(code),
  }),
);

const DAILY_STORY_POLL_INTERVAL_MS = 3_000;
const DAILY_STORY_POLL_MAX_MS = 10 * 60_000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function listDailyStories(params: {
  status?: string;
  story_type?: string;
  /** 按 key 模糊搜索（后端 LIKE） */
  key?: string;
  /** true=仅有关联任务；false=仅无任务 */
  has_job?: boolean;
  limit?: number;
  offset?: number;
} = {}): Promise<DailyStoryListResponse> {
  const response = await api.get<DailyStoryListResponse>("/v_factory/api/daily_story/list", {
    params,
  });
  return response.data;
}

export async function getDailyStory(id: number): Promise<DailyStoryRecord> {
  const response = await api.get<DailyStoryRecord>("/v_factory/api/daily_story/get", {
    params: { id },
  });
  return response.data;
}

/** 轮询直到 status 不再是 processing；超时仍返回最后一次结果。 */
export async function waitDailyStoryReady(
  storyId: number,
  {
    intervalMs = DAILY_STORY_POLL_INTERVAL_MS,
    maxWaitMs = DAILY_STORY_POLL_MAX_MS,
  }: { intervalMs?: number; maxWaitMs?: number } = {}
): Promise<DailyStoryRecord> {
  const started = Date.now();
  let latest = await getDailyStory(storyId);
  while (latest.status === "processing" && Date.now() - started < maxWaitMs) {
    await sleep(intervalMs);
    latest = await getDailyStory(storyId);
  }
  return latest;
}

export async function generateDailyStory(
  theme: string,
  opts?: { storyType?: string | null },
): Promise<DailyStoryRecord> {
  const story_type = (opts?.storyType ?? "").trim().toUpperCase().slice(0, 1) || undefined;
  const response = await api.post<DailyStoryRecord>("/v_factory/api/daily_story/generate", {
    theme,
    ...(story_type ? { story_type } : {}),
  });
  return response.data;
}

export async function deleteDailyStories(ids: number[]): Promise<{ deleted: number; ids: number[] }> {
  const response = await api.post<{ deleted: number; ids: number[] }>(
    "/v_factory/api/daily_story/delete",
    { ids }
  );
  return response.data;
}

export interface DailyStoryThemeItem {
  theme: string;
  /** 可适配的矛盾类型 A–G，首项为主类型 */
  story_types: string[];
}

function normalizeThemeItem(item: unknown): DailyStoryThemeItem | null {
  if (typeof item === "string") {
    const theme = item.trim();
    return theme ? { theme, story_types: [] } : null;
  }
  if (!item || typeof item !== "object") return null;
  const row = item as Record<string, unknown>;
  const theme = String(row.theme ?? "").trim();
  if (!theme) return null;
  let story_types: string[] = [];
  if (Array.isArray(row.story_types)) {
    story_types = row.story_types
      .map((c) => String(c ?? "").trim().toUpperCase().slice(0, 1))
      .filter((c) => c in DAILY_STORY_TYPE_LABELS);
  } else if (row.story_type) {
    const c = String(row.story_type).trim().toUpperCase().slice(0, 1);
    if (c in DAILY_STORY_TYPE_LABELS) story_types = [c];
  }
  // 去重保序
  story_types = [...new Set(story_types)];
  return { theme, story_types };
}

export async function generateDailyStoryThemes(
  count: number = 15,
  opts?: { exclude?: string[] },
): Promise<DailyStoryThemeItem[]> {
  const response = await api.post<unknown[]>(
    "/v_factory/api/daily_story/themes",
    { count, exclude: opts?.exclude ?? [] },
    { timeout: 60_000 }
  );
  const raw = Array.isArray(response.data) ? response.data : [];
  return raw
    .map(normalizeThemeItem)
    .filter((item): item is DailyStoryThemeItem => item != null);
}

export async function createDailyStoryJob(storyId: number, params?: { speechRate?: number; lineGap?: number }): Promise<any> {
  const response = await api.post("/v_factory/api/daily_story/create_job", {
    id: storyId,
    speech_chars_per_sec: params?.speechRate,
    phrase_gap_sec: params?.lineGap,
  });
  return response.data;
}

export async function updateDailyStory(
  storyId: number,
  story: StoryContent
): Promise<DailyStoryRecord> {
  const response = await api.post<DailyStoryRecord>("/v_factory/api/daily_story/update", {
    id: storyId,
    story,
  });
  return response.data;
}

export async function regenerateDailyStory(storyId: number): Promise<DailyStoryRecord> {
  const response = await api.post<DailyStoryRecord>("/v_factory/api/daily_story/regenerate", {
    id: storyId,
  });
  return response.data;
}

export async function syncDailyStoryToJob(
  storyId: number,
  story?: StoryContent
): Promise<{ id: number }> {
  const response = await api.post("/v_factory/api/daily_story/sync_to_job", {
    id: storyId,
    story,
  });
  return response.data;
}
