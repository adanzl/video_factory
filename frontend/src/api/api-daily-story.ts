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
  job_id: number | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export type DailyStoryListResponse = ListResponse<DailyStoryRecord>;

const DAILY_STORY_POLL_INTERVAL_MS = 3_000;
const DAILY_STORY_POLL_MAX_MS = 10 * 60_000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function listDailyStories(params: {
  status?: string;
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

export async function generateDailyStory(theme: string): Promise<DailyStoryRecord> {
  const response = await api.post<DailyStoryRecord>("/v_factory/api/daily_story/generate", {
    theme,
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

export async function generateDailyStoryThemes(count: number = 15): Promise<string[]> {
  const response = await api.post<string[]>(
    "/v_factory/api/daily_story/themes",
    { count },
    { timeout: 60_000 }
  );
  return Array.isArray(response.data) ? response.data : [];
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
