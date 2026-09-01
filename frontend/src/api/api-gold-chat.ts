import { api } from "./config";
import type { ListResponse } from "@/types";
import type { DialogueLine, StoryContent } from "./api-daily-story";
import { formatDailyStoryType } from "./api-daily-story";

export interface GoldChatListItem {
  id: number;
  source_id: string;
  url?: string;
  title: string;
  bili_title?: string;
  status: string;
  mechanism: string;
  structure_type: string;
  conflict_core?: string;
  auto_score?: number;
  has_gold_chat: boolean;
  chat_chars?: number;
  chat_lines?: number;
  scene_title?: string;
  exported_at?: string;
  gold_chat_daily_story_id?: number | null;
  updated_at?: string;
}

export type GoldChatListResponse = ListResponse<GoldChatListItem>;

export interface GoldStoryDump {
  story_raw?: string;
  perspective?: string;
  funny_why?: string;
  beat?: string[];
  banned_literals?: string[];
  dialogue_seed?: Array<{ speaker?: string; intent?: string }>;
  setting?: string;
  closing_intent?: string;
  speaker_map_note?: string;
  scene_contract?: Record<string, unknown>;
  source_type?: string;
  transcript_path?: string;
}

export interface GoldChatPayload {
  chat_chars?: number;
  chat_lines?: number;
  exported_at?: string;
  export_missing?: boolean;
  scene_title?: string;
  daily_story?: StoryContent;
  gold_meta?: Record<string, unknown>;
}

export interface GoldStoryAudit {
  pass?: boolean;
  stage?: string;
  reject_reasons?: string[];
  audit_notes?: string;
  llm_scores?: {
    sibling_fit?: number;
    age_fit?: number;
    conflict_usable?: number;
    mapping_fit?: number;
  };
}

export interface GoldChatErrorInfo {
  error: string;
  failed_at?: string;
}

export interface GoldStoryDetail {
  id?: number;
  source_id: string;
  url?: string;
  title?: string;
  bili_title?: string;
  mechanism?: string;
  structure_type?: string;
  status?: string;
  conflict_core?: string;
  auto_score?: number;
  gold_chat_daily_story_id?: number | null;
  audit?: GoldStoryAudit | null;
  dump: GoldStoryDump;
  has_gold_chat: boolean;
  gold_chat?: GoldChatPayload | null;
  gold_chat_error?: GoldChatErrorInfo | null;
}

export interface GoldStoryTranscript {
  id?: number;
  source_id: string;
  title?: string;
  url?: string;
  transcript_backend?: string;
  transcript_path?: string | null;
  transcript_repaired_path?: string | null;
  transcript_repair_confidence?: number;
  transcript_speakers?: string[];
  transcript_repair_notes?: string;
  has_transcript: boolean;
  has_repaired: boolean;
  transcript_raw: string;
  transcript_repaired: string;
  transcript: string;
  transcript_raw_chars: number;
  transcript_repaired_chars: number;
  transcript_chars: number;
}

/** @deprecated 兼容旧引用，请用 GoldStoryDetail */
export type GoldChatExport = GoldStoryDetail;

export interface GoldChatImportResult {
  action: "insert" | "update" | "skip";
  reason?: string;
  source_id?: string;
  gold_story_id?: number;
  daily_story_id?: number;
  theme?: string;
  story_type?: string;
  daily_story?: StoryContent;
}

export interface GoldChatConvertResult {
  action: "ok" | "skip";
  reason?: string;
  source_id?: string;
  gold_story_id?: number;
  chat_chars?: number;
  chat_lines?: number;
  scene_title?: string;
  daily_story?: StoryContent;
  export?: GoldChatExport;
}

export interface GoldChatBatchResult {
  workflow: string;
  requested: number;
  selected: number;
  ok: number;
  skipped: number;
  failed: number;
  export_dir?: string;
  results: Array<{
    source_id: string;
    gold_story_id?: number;
    title?: string;
    action: string;
    reason?: string;
    error?: string;
    chat_chars?: number;
    chat_lines?: number;
  }>;
  batch_report?: { json?: string; markdown?: string };
}

export type GoldStoryCollectStatus = "idle" | "running" | "done" | "error";

/** 采集任务状态（含入队 / 异步 OCR 进度） */
export interface GoldStoryCollectResult {
  workflow: string;
  status: GoldStoryCollectStatus;
  max?: number;
  /** enqueue | enqueued | process | done */
  phase?: string;
  candidates?: number;
  /** H0/H1 已 pending 入库条数 */
  enqueued?: number;
  /** 队列已处理条数（OCR+结构化） */
  processed?: number;
  inserted?: number;
  inserted_rejected?: number;
  gate_rejected?: number;
  skipped?: number;
  failed?: number;
  candidates_file?: string;
  error?: string | null;
  started_at?: number;
  finished_at?: number;
  results?: Array<{
    source_id?: string;
    title?: string;
    action: string;
    reason?: string;
    status?: string;
    id?: number;
    error?: string;
  }>;
}

export type GoldStoryReimportStatus = GoldStoryCollectStatus;

export interface GoldStoryReimportResult {
  workflow: string;
  status: GoldStoryReimportStatus;
  ids?: number[];
  source_ids?: string[];
  force_transcript?: boolean;
  requested?: number;
  updated?: number;
  inserted?: number;
  rejected?: number;
  failed?: number;
  ok?: number;
  error?: string | null;
  started_at?: number;
  finished_at?: number;
  results?: Array<{
    source_id?: string;
    title?: string;
    action: string;
    reason?: string;
    status?: string;
    id?: number;
    error?: string;
  }>;
}

export { formatDailyStoryType };

export function formatAutoScore(score?: number | null): string {
  if (score == null || Number.isNaN(score)) return "-";
  return score.toFixed(2);
}

export async function listGoldChats(params: {
  /** true=已导入日常故事；false=未导入 */
  has_story?: boolean;
  /** 排除已驳回条目 */
  exclude_rejected?: boolean;
  limit?: number;
  offset?: number;
} = {}): Promise<GoldChatListResponse> {
  const response = await api.get<GoldChatListResponse>(
    "/v_factory/api/gold_chat/list",
    { params },
  );
  return response.data;
}

export async function getGoldChat(params: {
  id?: number;
  sourceId?: string;
}): Promise<GoldStoryDetail> {
  const response = await api.get<GoldStoryDetail>(
    "/v_factory/api/gold_chat/get",
    {
      params: {
        id: params.id,
        source_id: params.sourceId,
      },
    },
  );
  return response.data;
}

export async function getGoldStoryTranscript(params: {
  id?: number;
  sourceId?: string;
}): Promise<GoldStoryTranscript> {
  const response = await api.get<GoldStoryTranscript>(
    "/v_factory/api/gold_chat/transcript",
    {
      params: {
        id: params.id,
        source_id: params.sourceId,
      },
    },
  );
  return response.data;
}

export async function convertGoldChat(params: {
  id?: number;
  sourceId?: string;
  force?: boolean;
}): Promise<GoldChatConvertResult> {
  const response = await api.post<GoldChatConvertResult>(
    "/v_factory/api/gold_chat/convert",
    {
      id: params.id,
      source_id: params.sourceId,
      force: params.force ?? false,
    },
    { timeout: 120_000 },
  );
  return response.data;
}

export interface GoldStoryDeleteResult {
  deleted: number;
  ids: number[];
  files_removed: number;
  results: Array<{
    id: number;
    source_id?: string;
    action: string;
    error?: string;
  }>;
}

export async function deleteGoldStories(ids: number[]): Promise<GoldStoryDeleteResult> {
  const response = await api.post<GoldStoryDeleteResult>(
    "/v_factory/api/gold_chat/delete",
    { ids },
  );
  return response.data;
}

export async function collectGoldStories(params: {
  max?: number;
} = {}): Promise<GoldStoryCollectResult> {
  const response = await api.post<GoldStoryCollectResult>(
    "/v_factory/api/gold_chat/collect",
    { max: params.max ?? 10 },
  );
  return response.data;
}

export async function getGoldStoryCollectStatus(): Promise<GoldStoryCollectResult> {
  const response = await api.get<GoldStoryCollectResult>(
    "/v_factory/api/gold_chat/collect",
  );
  return response.data;
}

export async function reimportGoldStories(params: {
  ids?: number[];
  sourceId?: string;
  sourceIds?: string[];
  forceTranscript?: boolean;
} = {}): Promise<GoldStoryReimportResult> {
  const response = await api.post<GoldStoryReimportResult>(
    "/v_factory/api/gold_chat/reimport",
    {
      ids: params.ids,
      source_id: params.sourceId,
      source_ids: params.sourceIds,
      force_transcript: params.forceTranscript ?? true,
    },
  );
  return response.data;
}

export async function getGoldStoryReimportStatus(): Promise<GoldStoryReimportResult> {
  const response = await api.get<GoldStoryReimportResult>(
    "/v_factory/api/gold_chat/reimport",
  );
  return response.data;
}

export async function batchConvertGoldChat(params: {
  max?: number;
  status?: string;
  ids?: number[];
  sourceIds?: string[];
  force?: boolean;
} = {}): Promise<GoldChatBatchResult> {
  const response = await api.post<GoldChatBatchResult>(
    "/v_factory/api/gold_chat/batch",
    {
      max: params.max ?? 10,
      status: params.status ?? "active",
      ids: params.ids,
      source_ids: params.sourceIds,
      force: params.force ?? false,
    },
    { timeout: 600_000 },
  );
  return response.data;
}

export async function importGoldChat(params: {
  id?: number;
  sourceId?: string;
  force?: boolean;
}): Promise<GoldChatImportResult> {
  const response = await api.post<GoldChatImportResult>(
    "/v_factory/api/gold_chat/import",
    {
      id: params.id,
      source_id: params.sourceId,
      force: params.force ?? false,
    },
  );
  return response.data;
}

export interface GoldStoryRejectResult {
  rejected: number;
  skipped: number;
  ids: number[];
  results: Array<{
    id: number;
    source_id?: string;
    action: string;
    status?: string;
    prev_status?: string | null;
    reason?: string;
    error?: string;
  }>;
}

export async function rejectGoldStories(ids: number[]): Promise<GoldStoryRejectResult> {
  const response = await api.post<GoldStoryRejectResult>(
    "/v_factory/api/gold_chat/reject",
    { ids },
  );
  return response.data;
}

export function calcChatChars(dialogue?: DialogueLine[]): number {
  if (!dialogue?.length) return 0;
  return dialogue.reduce((sum, d) => sum + (d.line?.length || 0), 0);
}
