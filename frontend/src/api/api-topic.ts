/**
 * 选题 API
 */
import { api } from "./config";

export interface TopicItem {
  title: string;
  track?: string;
  template?: string;
  hook?: string;
}

export interface GenerateTopicsParams {
  theme?: string;
  count?: number;
  system_prompt?: string;
  user_prompt?: string;
}

export interface GenerateTopicsResult {
  theme: string;
  count: number;
  topics: TopicItem[];
  titles: string[];
}

export async function generateTopics(params: GenerateTopicsParams): Promise<GenerateTopicsResult> {
  const response = await api.post<GenerateTopicsResult>("/v_factory/api/topic/gen", params);
  return response.data;
}
