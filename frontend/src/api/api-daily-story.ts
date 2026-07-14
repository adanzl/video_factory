import { api } from "./config";
import type { ListResponse } from "@/types";

export interface DialogueLine {
  speaker: string;
  line: string;
}

export interface StoryContent {
  scene_title: string;
  setting: string;
  dialogue: DialogueLine[];
  punchline_explain: string;
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

const DAILY_STORY_LLM_TIMEOUT_MS = 120_000;

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

export async function generateDailyStory(theme: string): Promise<DailyStoryRecord> {
  const response = await api.post<DailyStoryRecord>(
    "/v_factory/api/daily_story/generate",
    { theme },
    { timeout: DAILY_STORY_LLM_TIMEOUT_MS }
  );
  return response.data;
}

export async function deleteDailyStories(ids: number[]): Promise<{ deleted: number; ids: number[] }> {
  const response = await api.post<{ deleted: number; ids: number[] }>(
    "/v_factory/api/daily_story/delete",
    { ids }
  );
  return response.data;
}

export async function generateDailyStoryThemes(count: number = 2): Promise<string[]> {
  const response = await api.post<string[]>(
    "/v_factory/api/daily_story/themes",
    { count },
    { timeout: 60_000 }
  );
  return Array.isArray(response.data) ? response.data : [];
}

export async function createDailyStoryJob(storyId: number): Promise<any> {
  const response = await api.post("/v_factory/api/daily_story/create_job", { id: storyId });
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
  const response = await api.post<DailyStoryRecord>(
    "/v_factory/api/daily_story/regenerate",
    { id: storyId },
    { timeout: DAILY_STORY_LLM_TIMEOUT_MS }
  );
  return response.data;
}
