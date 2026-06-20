/**
 * 选题 API
 */
import { api } from "./config";
import type {
  EnqueueRunMode,
  EnqueueTopicsParams,
  EnqueueTopicsResult,
  GenerateAndSaveResult,
  GenerateTopicsParams,
  GenerateTopicsResult,
  ListTitlesParams,
  ScoreTopicsResult,
  TitleRecord,
} from "@/types/topic";

export type { TopicItem } from "@/types/topic";

export async function listTitles(params: ListTitlesParams = {}): Promise<TitleRecord[]> {
  const response = await api.get<TitleRecord[]>("/v_factory/api/topic/list", { params });
  return Array.isArray(response.data) ? response.data : [];
}

export async function generateTopics(
  params: GenerateTopicsParams
): Promise<GenerateTopicsResult | GenerateAndSaveResult> {
  const response = await api.post<GenerateTopicsResult | GenerateAndSaveResult>(
    "/v_factory/api/topic/gen",
    params
  );
  return response.data;
}

export async function scoreTopics(ids?: number[]): Promise<ScoreTopicsResult> {
  const response = await api.post<ScoreTopicsResult>("/v_factory/api/topic/score", {
    ids: ids ?? [],
  });
  return response.data;
}

export async function enqueueTopics(
  params: EnqueueTopicsParams = {}
): Promise<EnqueueTopicsResult> {
  const response = await api.post<EnqueueTopicsResult>("/v_factory/api/topic/enqueue", {
    ids: params.ids ?? [],
    skip_publish: params.skip_publish ?? true,
    run_mode: params.run_mode ?? "script",
  });
  return response.data;
}

export async function deleteTopics(ids: number[]): Promise<{ deleted: number; ids: number[] }> {
  const response = await api.post("/v_factory/api/topic/delete", { ids });
  return response.data;
}
