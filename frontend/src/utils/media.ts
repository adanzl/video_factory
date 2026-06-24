import { api } from "@/api/config";
import type { FinalAsset } from "@/types/jobs";

/**
 * 将本地媒体绝对路径转为可通过 HTTP 访问的 URL
 */
export function getMediaFileUrl(filePath: string): string {
  if (!filePath || typeof filePath !== "string" || filePath.trim() === "") {
    return "";
  }

  try {
    const baseURL = api.defaults.baseURL || "";
    if (!baseURL || typeof baseURL !== "string") {
      return "";
    }

    const normalized = filePath.trim().replace(/\\/g, "/");
    const path = normalized.startsWith("/") ? normalized.slice(1) : normalized;
    if (!path) {
      return "";
    }

    const encodedPath = path
      .split("/")
      .map(part => encodeURIComponent(part))
      .join("/");
    const mediaUrl = `${baseURL.replace(/\/$/, "")}/v_factory/api/media/files/${encodedPath}`;

    if (mediaUrl.includes("index.html") || mediaUrl.endsWith(".html")) {
      return "";
    }

    return mediaUrl;
  } catch {
    return "";
  }
}

/** 格式化文件大小 */
export function formatFileSize(bytes?: number | null): string {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes) || bytes < 0) {
    return "-";
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  if (bytes < 1024 * 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

/** 从 final_path 字段解析成片路径（兼容旧字符串） */
export function resolveFinalPath(finalPath?: FinalAsset | string | null): string {
  if (!finalPath) {
    return "";
  }
  if (typeof finalPath === "string") {
    return finalPath.trim();
  }
  return finalPath.path?.trim() ?? "";
}

/** 格式化处理耗时（秒） */
export function formatCostTime(seconds?: number | null): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) {
    return "-";
  }
  return `${seconds.toFixed(1)} 秒`;
}

/** 中文口播约 5 字/秒，与后端 app/utils/media 对齐 */
const NARRATION_CHARS_PER_SEC = 5;
const NARRATION_FILL_RATIO = 0.92;
const NARRATION_MAX_CHARS = 3000;

/** 默认目标成片时长（秒），与 TARGET_FINAL_DURATION_SEC 对齐 */
export const DEFAULT_TARGET_FINAL_DURATION_SEC = 360;
/** 口播字数估算时扣除的片头预算（秒） */
export const INTRO_DURATION_BUDGET_SEC = 2;

/** 按基底/目标视频时长估算推荐口播字数 */
export function estimateNarrationTargetWords(durationSec: number): number {
  const target = Math.floor(durationSec * NARRATION_CHARS_PER_SEC * NARRATION_FILL_RATIO);
  return Math.max(1, Math.min(NARRATION_MAX_CHARS, target));
}

/** standard 线默认口播目标字数 */
export function defaultNarrationTargetWords(
  targetFinalSec = DEFAULT_TARGET_FINAL_DURATION_SEC
): number {
  const body = Math.max(30, targetFinalSec - INTRO_DURATION_BUDGET_SEC);
  return estimateNarrationTargetWords(body);
}

/** 按成片分钟数估算口播字数（5 字/秒，与后端对齐） */
export function narrationTargetForMinutes(
  minutes: number,
  charsPerSec = NARRATION_CHARS_PER_SEC,
  introBudgetSec = INTRO_DURATION_BUDGET_SEC
): number {
  const body = Math.max(30, minutes * 60 - introBudgetSec);
  const target = Math.floor(body * charsPerSec * NARRATION_FILL_RATIO);
  return Math.max(1, Math.min(NARRATION_MAX_CHARS, target));
}

/** 由口播目标字数反推预计成片时长（分钟，含片头预算） */
export function estimatedMinutesFromNarrationWords(
  words: number,
  introBudgetSec = INTRO_DURATION_BUDGET_SEC
): number {
  if (!Number.isFinite(words) || words <= 0) {
    return 1;
  }
  const bodySec = words / (NARRATION_CHARS_PER_SEC * NARRATION_FILL_RATIO);
  const totalSec = Math.max(30, bodySec) + introBudgetSec;
  return Math.round((totalSec / 60) * 10) / 10;
}

/** 由预计成片时长（分钟）反推口播目标字数 */
export function narrationTargetFromEstimatedMinutes(
  minutes: number,
  introBudgetSec = INTRO_DURATION_BUDGET_SEC
): number {
  return narrationTargetForMinutes(minutes, NARRATION_CHARS_PER_SEC, introBudgetSec);
}

/** 格式化媒体时长（秒 → mm:ss） */
export function formatMediaDuration(seconds?: number | null): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) {
    return "-";
  }
  const total = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}
