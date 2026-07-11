import { api } from "./config";
import type {
  DeleteLowScoreTopicsResult,
  EnqueueTopicsParams,
  EnqueueTopicsResult,
  TopicCatalogResult,
  GenerateAndSaveResult,
  GenerateTopicsParams,
  GenerateTopicsResult,
  ListTitlesParams,
  OptimizeTopicResult,
  ScoreTopicsResult,
  TitleRecord,
  UpdateTitleParams,
} from "@/types/topic";

export type { TopicItem } from "@/types/topic";

/** 选题生成/优化走 LLM，偶发 >30s，与后端 DeepSeek timeout 对齐留余量 */
const TOPIC_LLM_TIMEOUT_MS = 120_000;

export async function listTitles(params: ListTitlesParams = {}): Promise<TitleRecord[]> {
  const response = await api.get<TitleRecord[]>("/v_factory/api/topic/list", { params });
  return Array.isArray(response.data) ? response.data : [];
}

export async function fetchTopicCatalog(): Promise<TopicCatalogResult> {
  const response = await api.get<TopicCatalogResult>("/v_factory/api/topic/catalog");
  return response.data;
}

export async function generateTopics(
  params: GenerateTopicsParams
): Promise<GenerateTopicsResult | GenerateAndSaveResult> {
  const response = await api.post<GenerateTopicsResult | GenerateAndSaveResult>(
    "/v_factory/api/topic/gen",
    params,
    { timeout: TOPIC_LLM_TIMEOUT_MS }
  );
  return response.data;
}

export async function optimizeTopic(id: number, direction?: string): Promise<OptimizeTopicResult> {
  const response = await api.post<OptimizeTopicResult>(
    "/v_factory/api/topic/optimize",
    { id, direction: direction || undefined },
    { timeout: TOPIC_LLM_TIMEOUT_MS }
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

export async function updateTopic(params: UpdateTitleParams): Promise<{ title: TitleRecord }> {
  const response = await api.post<{ title: TitleRecord }>("/v_factory/api/topic/update", params);
  return response.data;
}

export async function deleteTopics(ids: number[]): Promise<{ deleted: number; ids: number[] }> {
  const response = await api.post("/v_factory/api/topic/delete", { ids });
  return response.data;
}

export async function deleteLowScoreTopics(
  maxScore = 75
): Promise<DeleteLowScoreTopicsResult> {
  const response = await api.post<DeleteLowScoreTopicsResult>(
    "/v_factory/api/topic/delete-low",
    { max_score: maxScore }
  );
  return response.data;
}
