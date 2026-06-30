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
    const trimmed = finalPath.trim();
    if (trimmed.startsWith("{")) {
      try {
        const data = JSON.parse(trimmed) as FinalAsset;
        return data.path?.trim() ?? "";
      } catch {
        return trimmed;
      }
    }
    return trimmed;
  }
  return finalPath.path?.trim() ?? "";
}

/** 从 final_path 字段解析成片时长（秒，兼容旧字符串） */
export function resolveFinalDuration(finalPath?: FinalAsset | string | null): number | null {
  if (!finalPath) {
    return null;
  }
  if (typeof finalPath === "string") {
    const trimmed = finalPath.trim();
    if (!trimmed.startsWith("{")) {
      return null;
    }
    try {
      const data = JSON.parse(trimmed) as FinalAsset;
      const duration = data?.duration;
      return typeof duration === "number" && !Number.isNaN(duration) ? duration : null;
    } catch {
      return null;
    }
  }
  const duration = finalPath.duration;
  return typeof duration === "number" && !Number.isNaN(duration) ? duration : null;
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

export const MEDIA_PREVIEW_MAX_VIEWPORT_RATIO = 0.7;
export const MEDIA_PREVIEW_MAX_WIDTH_PX = 420;
/** 跨域媒体预览需 CORS；避免 Chrome ORB 拦截 */
export const MEDIA_CROSS_ORIGIN = "anonymous";

export type CssSizeStyle = Record<string, string>;

export type MediaPreviewBoxOptions = {
  maxWidthPx?: number;
  maxViewportRatio?: number;
};

function parseAspectRatio(ratio: string): number {
  const [width, height] = ratio.split("/").map(part => Number.parseFloat(part.trim()));
  if (!width || !height) {
    return 16 / 9;
  }
  return width / height;
}

/** 按视频/图片 intrinsic 尺寸计算预览容器样式（横竖屏均不裁切） */
export function buildMediaPreviewBoxStyle(
  width?: number | null,
  height?: number | null,
  fallbackAspectRatio = "16 / 9",
  options?: MediaPreviewBoxOptions
): CssSizeStyle {
  const maxWidthPx = options?.maxWidthPx ?? MEDIA_PREVIEW_MAX_WIDTH_PX;
  const maxViewportRatio = options?.maxViewportRatio ?? MEDIA_PREVIEW_MAX_VIEWPORT_RATIO;

  if (width && height && width > 0 && height > 0) {
    const ratio = width / height;
    const maxH =
      (typeof window !== "undefined" ? window.innerHeight : 800) * maxViewportRatio;
    const maxW = Math.min(
      maxWidthPx,
      typeof window !== "undefined" ? window.innerWidth * 0.9 : maxWidthPx
    );

    let boxW: number;
    let boxH: number;
    if (ratio >= 1) {
      boxW = Math.min(maxW, maxH * ratio);
      boxH = boxW / ratio;
    } else {
      boxH = Math.min(maxH, maxW / ratio);
      boxW = boxH * ratio;
    }

    return {
      width: `${Math.round(boxW)}px`,
      height: `${Math.round(boxH)}px`,
    };
  }

  const ratio = parseAspectRatio(fallbackAspectRatio);
  const minHeight = Math.round(maxWidthPx / ratio);

  return {
    width: "100%",
    maxWidth: `${maxWidthPx}px`,
    aspectRatio: fallbackAspectRatio,
    minHeight: `${minHeight}px`,
  };
}

/** 片头预览在 metadata 未就绪时的占位比例 */
export function guessIntroPreviewAspectRatio(
  orientation: "auto" | "portrait" | "landscape",
  pipeline?: string | null
): string {
  if (orientation === "landscape") {
    return "16 / 9";
  }
  if (orientation === "portrait") {
    return "9 / 16";
  }
  return pipeline === "material" ? "16 / 9" : "9 / 16";
}

export function formatVideoResolution(
  width?: number | null,
  height?: number | null
): string {
  if (width && height && width > 0 && height > 0) {
    return `${width}×${height}`;
  }
  return "-";
}

/** 从 img / el-image 的 load 事件读取原始分辨率 */
export function readImageNaturalSize(event: Event): { width: number; height: number } | null {
  const target = event.target;
  const img =
    target instanceof HTMLImageElement
      ? target
      : event.currentTarget instanceof HTMLElement
        ? event.currentTarget.querySelector("img")
        : null;
  if (img instanceof HTMLImageElement && img.naturalWidth > 0 && img.naturalHeight > 0) {
    return { width: img.naturalWidth, height: img.naturalHeight };
  }
  return null;
}

/** 封面居中 4:3 区域参考线（两条边，百分比定位） */
export function computeCentered43GuideLines(
  width?: number | null,
  height?: number | null,
  fallbackRatio = 9 / 16
): { mode: "horizontal" | "vertical"; startPct: number; spanPct: number } {
  const ratio =
    width && height && width > 0 && height > 0 ? width / height : fallbackRatio;
  const target = 4 / 3;

  if (ratio <= target) {
    const spanPct = ratio * (3 / 4) * 100;
    return { mode: "horizontal", startPct: (100 - spanPct) / 2, spanPct };
  }

  const spanPct = (target / ratio) * 100;
  return { mode: "vertical", startPct: (100 - spanPct) / 2, spanPct };
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
