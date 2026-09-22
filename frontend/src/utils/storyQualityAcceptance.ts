import type { StoryQuality } from "@/api/api-daily-story";

export type AcceptanceTagType = "success" | "warning" | "danger" | "info";

export function acceptanceTags(quality: StoryQuality | undefined): string[] {
  if (!quality) {
    return ["语义待审"];
  }
  const tags: string[] = [];
  const struct = quality.structure_score ?? quality.score ?? 0;
  tags.push(struct >= 75 ? "结构合格" : "结构不足");
  if (quality.semantic_pass == null) {
    tags.push("语义待审");
  } else if (quality.semantic_pass) {
    tags.push("语义通过");
  } else {
    tags.push("语义未过");
  }
  if (quality.humor_pending || !quality.humor) {
    tags.push("好笑待审");
  } else {
    tags.push("好笑已评");
  }
  return tags;
}

export function acceptanceTagType(tag: string): AcceptanceTagType {
  if (tag === "结构合格" || tag === "语义通过" || tag === "好笑已评") {
    return "success";
  }
  if (tag === "语义待审" || tag === "好笑待审" || tag === "结构不足") {
    return "warning";
  }
  if (tag === "语义未过") {
    return "danger";
  }
  return "info";
}

/** 未完成语义或好笑审核时不展示综合 grade「好/中/偏弱」。 */
export function showCompositeGrade(quality: StoryQuality | undefined): boolean {
  if (!quality?.grade) {
    return false;
  }
  if (quality.semantic_pass == null) {
    return false;
  }
  if (quality.humor_pending) {
    return false;
  }
  return true;
}
