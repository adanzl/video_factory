import { api } from "./config";

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
  status: string;
  created_at: string;
  updated_at: string;
}

const DAILY_STORY_LLM_TIMEOUT_MS = 120_000;

export async function listDailyStories(params: {
  status?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<DailyStoryRecord[]> {
  const response = await api.get<DailyStoryRecord[]>("/v_factory/api/daily_story/list", {
    params,
  });
  return Array.isArray(response.data) ? response.data : [];
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
