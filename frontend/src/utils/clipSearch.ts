/** 片段搜索 UI 工具函数 */

import { CLIP_PROVIDER_LABELS } from "@/api/api-clips";
import type { ClipProviderName, ClipProviderSearchMeta, ClipSearchLanguage } from "@/types/clipSearch";

export type ClipOrientation = "" | "portrait" | "landscape" | "square";

export const clipSearchKeywordPlaceholder = (language: ClipSearchLanguage) => {
  if (language === "zh") {
    return "中文关键词，如 磁铁实验";
  }
  if (language === "en") {
    return "英文关键词，如 magnet experiment";
  }
  return "关键词，英文或中文均可";
};

export const providerLabel = (name: ClipProviderName) => CLIP_PROVIDER_LABELS[name] ?? name;

export const providerMetaTagType = (status: ClipProviderSearchMeta["status"]) => {
  if (status === "ok") return "success";
  if (status === "skipped") return "info";
  return "warning";
};

export const formatClipDuration = (seconds: number) => {
  const total = Math.max(0, Math.round(seconds));
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return mins > 0 ? `${mins}:${secs.toString().padStart(2, "0")}` : `${secs}s`;
};

export const buildSegmentClipSearchKeyword = (fields: {
  motion_prompt?: string | null;
  visual_brief?: string | null;
  image_prompt?: string | null;
  text?: string | null;
}) => {
  const candidates = [fields.motion_prompt, fields.visual_brief, fields.image_prompt, fields.text];
  for (const value of candidates) {
    const normalized = value?.replace(/\s+/g, " ").trim();
    if (normalized) {
      return normalized.length > 80 ? `${normalized.slice(0, 80)}…` : normalized;
    }
  }
  return "";
};
