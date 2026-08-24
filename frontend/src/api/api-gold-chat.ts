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
}

export type GoldChatListResponse = ListResponse<GoldChatListItem>;

export interface GoldChatExport {
  gold_story_id?: number;
  source_id: string;
  url?: string;
  title?: string;
  bili_title?: string;
  mechanism?: string;
  structure_type?: string;
  status?: string;
  conflict_core?: string;
  chat_chars?: number;
  chat_lines?: number;
  exported_at?: string;
  gold_chat_daily_story_id?: number | null;
  daily_story: StoryContent;
  gold_meta?: Record<string, unknown>;
  gold_story?: GoldChatListItem;
}

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

export { formatDailyStoryType };

export function formatAutoScore(score?: number | null): string {
  if (score == null || Number.isNaN(score)) return "-";
  return score.toFixed(2);
}

export async function listGoldChats(params: {
  status?: string;
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
}): Promise<GoldChatExport> {
  const response = await api.get<GoldChatExport>(
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

export function calcChatChars(dialogue?: DialogueLine[]): number {
  if (!dialogue?.length) return 0;
  return dialogue.reduce((sum, d) => sum + (d.line?.length || 0), 0);
}
