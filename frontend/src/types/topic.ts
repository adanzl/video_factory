/**
 * 选题类型
 */
export interface TopicItem {
  title: string;
  track?: string;
  template?: string;
  hook?: string;
}

export interface TitleRecord extends TopicItem {
  id: number;
  score?: number | null;
  score_detail?: ScoreDetail | null;
  status: TitleStatus;
  job_id?: number | null;
  source?: string;
  created_at?: string;
  updated_at?: string;
}

export type TitleStatus = "pending" | "queued" | "rejected" | "enqueued";

export interface ScoreDetail {
  visual: number;
  fact: number;
  curiosity: number;
  compliance: number;
  total: number;
  rejected_reason?: string | null;
}

export interface ListTitlesParams {
  status?: string;
  limit?: number;
  offset?: number;
}

export interface GenerateTopicsParams {
  theme?: string;
  count?: number;
  system_prompt?: string;
  user_prompt?: string;
  save?: boolean;
}

export interface GenerateTopicsResult {
  theme: string;
  count: number;
  topics: TopicItem[];
  titles: string[];
}

export interface GenerateAndSaveResult {
  theme: string;
  generated: number;
  added: TitleRecord[];
  skipped: number;
  count: number;
}

export interface ScoreTopicsResult {
  scored: TitleRecord[];
  count: number;
}

export type EnqueueRunMode = "none" | "script" | "full";

export interface EnqueueTopicsParams {
  ids?: number[];
  skip_publish?: boolean;
  run_mode?: EnqueueRunMode;
}

export interface ImportHotTopicsParams {
  limit?: number;
  count_per_theme?: number;
  l1_rules?: boolean;
  min_score?: number;
  use_theme_llm?: boolean;
}

export interface ImportHotTopicsResult {
  summary: {
    fetched: number;
    kept: number;
    rejected: number;
    themes?: number;
    topics?: number;
    queued?: number;
    l1_rules?: boolean;
  };
  added: TitleRecord[];
  skipped: number;
  count: number;
  source: string;
  themes?: { keyword: string; theme: string; track: string; reason: string }[];
  topics?: {
    title: string;
    theme: string;
    keyword: string;
    total: number;
    status: TitleStatus;
  }[];
}

export type TopicTaskStatus = "running" | "done" | "failed";

export interface TopicTaskResponse {
  task_id: string;
  kind: string;
  status: TopicTaskStatus;
  result?: ImportHotTopicsResult;
  error?: string;
}

export interface EnqueueTopicsResult {
  jobs: { id: number; title: string }[];
  count: number;
  run_mode: EnqueueRunMode;
}

export interface DeleteLowScoreTopicsResult {
  deleted: number;
  ids: number[];
  max_score: number;
}
